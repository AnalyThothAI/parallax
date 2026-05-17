# Spec — Token Profile Facts Read Model

**Status**: Superseded
**Date**: 2026-05-13
**Owner**: Codex with Qinghuan
**Scope**: resolved DEX asset profile facts, Token Radar/Search read surfaces, shared frontend profile card
**Related**:

- `docs/superpowers/specs/active/2026-05-12-gmgn-dex-market-provider-split-cn.md`
- `docs/superpowers/plans/active/2026-05-12-gmgn-dex-market-provider-split-plan-cn.md`
- `docs/superpowers/plans/active/2026-05-13-token-profile-facts-read-model-plan-cn.md`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `src/gmgn_twitter_intel/domains/token_intel/ARCHITECTURE.md`

> Superseded on 2026-05-17 by
> `docs/superpowers/specs/active/2026-05-17-token-profile-current-facts-hard-cut-cn.md`.
> This document described the first GMGN-only profile cache. Do not use it as the
> current implementation target; the newer spec hard-cuts public profile reads to
> canonical current facts projected from persisted GMGN OpenAPI, GMGN stream, and
> OKX DEX evidence.

## One-line decision

Add one asset-level profile fact read model, one GMGN-backed refresh worker, and one shared public `profile` contract consumed by Token Radar, Search Inspect, and the selected-token drawer. Do not put profile facts inside Radar scoring snapshots, and do not let API or frontend call GMGN directly.

## Background

The current GMGN provider split already exposes the exact-token profile capability. `AssetMarketProviders` has separate `dex_discovery_market`, `dex_quote_market`, `dex_candle_market`, `dex_profile_market`, and `stream_dex_market` roles in `src/gmgn_twitter_intel/app/runtime/providers_wiring.py:46`. `GmgnDexMarketProvider.token_profile(chain_id,address)` maps GMGN token info into `DexTokenProfile` fields such as `website`, `twitter_username`, `telegram`, `gmgn_url`, `geckoterminal_url`, `description`, logo, and banner in `src/gmgn_twitter_intel/app/runtime/providers_wiring.py:161`.

The underlying GMGN OpenAPI client already parses these profile fields. `GmgnTokenInfo` includes website, Twitter/X, Telegram, provider links, description, pool, dev, stat, link, and raw payload fields in `src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py:16`. `_token_info_from_response` extracts link fields in `src/gmgn_twitter_intel/integrations/gmgn/openapi_client.py:205`.

The domain provider contract already names profile as a resolved-token capability. `DexTokenProfile` is defined in `src/gmgn_twitter_intel/domains/asset_market/providers.py:52`, and `DexTokenProfileProvider.token_profile(chain_id,address)` requires exact `chain_id + address` in `src/gmgn_twitter_intel/domains/asset_market/providers.py:125`.

The runtime still only uses the resolved-token provider roles for quote/candle paths. `ResolutionRefreshWorker` accepts `dex_discovery_market` and `dex_quote_market`, then uses discovery and quote roles in `src/gmgn_twitter_intel/domains/asset_market/runtime/resolution_refresh_worker.py:46`. No worker currently calls `dex_profile_market`.

Public read surfaces do not expose profile facts. `/api/search/inspect` builds `SearchInspectService` with search, token radar, and target repositories only in `src/gmgn_twitter_intel/app/surfaces/api/http.py:160`. `/api/token-radar` builds `AssetFlowService` with `token_radar` and `live_market_gateway` in `src/gmgn_twitter_intel/app/surfaces/api/http.py:186`.

`AssetFlowService._public_row` emits intent, target, attention, anchor price, live market, resolution, score, factor snapshot, data health, and source event ids in `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:75`. `_target_from_snapshot` only returns target identity fields such as target type, id, symbol, chain, address, and market type in `src/gmgn_twitter_intel/domains/token_intel/read_models/asset_flow_service.py:113`.

`SearchInspectService._token_result` composes target timeline, posts, radar item, market overlay, and deterministic agent brief in `src/gmgn_twitter_intel/domains/token_intel/read_models/search_inspect_service.py:81`. It does not read a profile repository.

The frontend types mirror the same gap. `SearchTokenResult` contains target, timeline, posts, radar item, market overlay, and agent brief in `web/src/api/types.ts:257`. `AssetFlowTargetBlock` contains target identity and venue-ish fields but no official links in `web/src/api/types.ts:318`. `AssetFlowRow` contains intent, target, attention, source ids, anchor price, live market, resolution, factor snapshot, and data health in `web/src/api/types.ts:416`.

The selected-token drawer has tabs for Timeline, Posts, Score, Lab, and Accounts in `web/src/components/TokenDetailDrawer.tsx:33`. Search Intel token result renders the case header, metrics, timeline, Twitter results, deterministic brief, and radar panel in `web/src/components/SearchIntelPage.tsx:215`. Neither surface has a shared profile component.

The existing social enrichment harness is not immediately reusable as-is for token narrative jobs. `EnrichmentRepository.claim_next_job` marks non-`watched_social_event_extraction` jobs as dead in `src/gmgn_twitter_intel/domains/social_enrichment/repositories/enrichment_repository.py:146`. A future token narrative agent must either use a separate queue or first generalize that harness.

## Problem

Users cannot see official website, X/Twitter, Telegram, GMGN link, logo, description, or a reliable project profile in Token Radar, Search Inspect, or the selected-token panel, even when GMGN already has those facts for a resolved token. The root cause is not frontend rendering alone and not provider availability alone. The missing link is a persisted asset-level profile fact model and a shared read contract between provider workers, API read models, and frontend surfaces.

## First principles

1. **Profile facts are asset-level facts**. They enrich a resolved `Asset(chain_id,address)` and should not be duplicated inside each `token_radar_rows` scoring window.
2. **Provider calls stay in `asset_market`**. API handlers, Token Radar projection, Search read models, and React components consume persisted facts only.
3. **One public profile contract**. Token Radar rows, Search Inspect token results, and the selected-token drawer must use the same `TokenProfileBlock` semantics.
4. **Agent output is not source-of-truth data**. A future narrative agent may consume profile facts and tweets, but official links and descriptions must be visible without running an agent.
5. **Failure is explicit and local**. Missing GMGN profile, rate limits, and provider errors become profile statuses, not hidden fallbacks or blocking API failures.

## Goals

- **G1 Persist profile facts**: Create an `asset_profiles` current-state table keyed by `(asset_id, provider)` with canonical profile columns, raw payload, freshness, and error fields.
- **G2 Hydrate from GMGN only after resolution**: Add an asset profile refresh worker that selects recent resolved DEX assets, calls `dex_profile_market.token_profile(chain_id,address)`, and upserts profile facts.
- **G3 Provider-free public reads**: Add a `TokenProfileReadModel` or equivalent read service that reads `asset_profiles` and returns one normalized `TokenProfileBlock`; public API/read models do not call GMGN.
- **G4 Shared API contract**: Attach the same nullable `profile` block to `/api/token-radar` rows and `/api/search/inspect` `token_result`.
- **G5 Shared frontend component**: Add one `TokenProfileCard` and render it in both `TokenDetailDrawer` and Search Intel token details.
- **G6 Deterministic first, narrative agent deferred**: Keep the initial release deterministic. Document the future narrative agent path without adding it to this implementation.
- **G7 No compatibility branches**: Do not preserve old profile behavior or add multi-provider fallback code, because no old profile behavior exists.

## Non-goals

- Do not replace OKX discovery search with GMGN.
- Do not replace OKX DEX WebSocket live price with GMGN.
- Do not use GMGN public Twitter WebSocket as a token profile source.
- Do not put website/Twitter/description into `token_radar_rows.factor_snapshot_json`.
- Do not make Search Inspect or Token Radar perform request-time provider calls.
- Do not implement the one-click narrative agent in this pass.
- Do not add website scraping in this pass.
- Do not create a generic provider arbitration layer.

## Target architecture

The target architecture adds a narrow asset profile lane beside market facts:

```mermaid
flowchart TD
  A["GMGN public Twitter stream"] --> B["events + token evidence"]
  B --> C["resolver"]
  C -->|Asset(chain,address)| D["registry_assets"]
  D --> E["AssetProfileRefreshWorker"]
  E --> F["GMGN dex_profile_market.token_profile"]
  F --> G["asset_profiles current facts"]
  G --> H["TokenProfileReadModel"]
  H --> I["/api/token-radar rows"]
  H --> J["/api/search/inspect token_result"]
  I --> K["TokenProfileCard in selected-token drawer"]
  J --> L["TokenProfileCard in Search Intel"]
```

Ownership boundaries:

- `asset_market` owns provider calls, profile persistence, refresh selection, freshness, and provider error status.
- `token_intel` owns Radar/Search composition and may read profile facts through a read-model interface.
- `app/runtime` wires the profile worker from `providers.asset_market.dex_profile_market`.
- `web` owns presentation only and receives normalized URLs from the API.

## Conceptual data flow

```text
resolved Asset(chain,address)
  -> select due profile refresh
  -> GMGN exact token profile lookup
  -> asset_profiles upsert
  -> TokenProfileReadModel.profile_for_targets
  -> /api/token-radar row.profile
  -> /api/search/inspect token_result.profile
  -> TokenProfileCard shared by Radar drawer and Search Intel
```

The new arrow starts after deterministic resolution. GMGN profile data must not create or change resolution; it only enriches an already-resolved asset.

## Core models

### AssetProfile

Current-state profile fact for one asset/provider pair.

Semantic fields:

- `asset_id`
- `provider`
- `status`: `ready`, `missing`, `unsupported`, or `error`
- identity: `symbol`, `name`, `logo_url`, `banner_url`, `description`
- links: `website_url`, `twitter_username`, `twitter_url`, `telegram_url`, `gmgn_url`, `geckoterminal_url`
- provenance: `raw_payload_json`, `observed_at_ms`, `updated_at_ms`, `next_refresh_at_ms`, `last_error`

Invariant: only resolved DEX assets may have GMGN profile rows. CEX tokens and unresolved intents return unsupported/missing profile blocks.

### TokenProfileBlock

Public API block shared by Radar and Search.

Semantic shape:

```json
{
  "status": "ready",
  "provider": "gmgn_dex_profile",
  "observed_at_ms": 123,
  "identity": {
    "symbol": "ABC",
    "name": "ABC Token",
    "logo_url": "https://assets.example/abc.png",
    "banner_url": "https://assets.example/abc-banner.png",
    "description": "ABC Token project profile."
  },
  "links": {
    "website_url": "https://abc.example",
    "twitter_url": "https://x.com/abc",
    "twitter_username": "abc",
    "telegram_url": "https://t.me/abc",
    "gmgn_url": "https://gmgn.ai/eth/token/0xabc",
    "geckoterminal_url": "https://www.geckoterminal.com/eth/pools/0xpool"
  },
  "source": {
    "provider": "gmgn_dex_profile",
    "raw_available": true,
    "last_error": null
  }
}
```

Public statuses are `ready`, `pending`, `missing`, `unsupported`, or `error`. `pending` means no persisted provider row exists yet for a resolved DEX asset; it is a read-model state, not an `asset_profiles` table row.

Invariant: URL normalization happens server-side. The frontend does not derive X/Twitter or GMGN URLs from provider-specific raw payloads.

### AssetProfileRefreshResult

Operational result from a single refresh loop.

Semantic fields:

- `selected`
- `refreshed`
- `ready`
- `missing`
- `error`
- `skipped`
- `provider`
- `started_at_ms`
- `finished_at_ms`

Invariant: worker result explains absence of profile data without blocking Radar/Search.

## Interface contracts

### `/api/token-radar`

Each returned row in `targets` and `attention` includes `profile` when the target is a resolved DEX asset. For resolved DEX assets with ready profile facts, `profile.status = "ready"`. For resolved assets not yet fetched, `profile.status = "pending"`. For fetched assets with no provider profile, `profile.status = "missing"`. For provider errors, `profile.status = "error"`. For CEX/unresolved rows, profile is absent or unsupported.

Existing ranking, scoring, anchor price, live market, and factor snapshot semantics do not change.

### `/api/search/inspect`

When `query.result_kind = "token_result"`, `token_result.profile` uses the same `TokenProfileBlock` shape as Token Radar rows. Search Inspect continues to return timeline, posts, market overlay, and deterministic brief even when profile is missing.

### CLI `asset-flow`

CLI output should match `/api/token-radar` profile semantics so operators can inspect the same contract without opening the frontend.

### Runtime health

The runtime health payload may include profile worker status: running flag, last result, last run time, last error, and configured provider status. Missing GMGN config should produce `unsupported` profile status, not API errors.

## Acceptance criteria

- **AC1**. WHEN GMGN profile provider is configured and a resolved DEX asset is due for refresh THEN the profile worker SHALL call `dex_profile_market.token_profile(chain_id,address)` and upsert an `asset_profiles` row.
- **AC2**. WHEN GMGN returns website/Twitter/Telegram/description/logo/banner fields THEN `asset_profiles` SHALL persist those fields with provider `gmgn_dex_profile`, raw payload, observed time, and next refresh time.
- **AC3**. WHEN GMGN returns no profile for a resolved asset THEN the system SHALL persist an explicit `missing` profile row with bounded retry time.
- **AC4**. WHEN GMGN lookup raises an error THEN the system SHALL persist or update an explicit `error` state with `last_error` and retry backoff, without failing Token Radar or Search Inspect requests.
- **AC5**. WHEN `/api/token-radar` returns a resolved DEX asset with ready profile facts THEN the corresponding row SHALL include `profile.status = "ready"` and normalized official links.
- **AC6**. WHEN `/api/search/inspect` returns a token result for the same asset THEN `token_result.profile` SHALL match the same profile contract and normalized links.
- **AC7**. WHEN Token Radar projection, Search Inspect read model, or HTTP handler runs THEN it SHALL NOT call GMGN or any external provider for profile data.
- **AC8**. WHEN a user opens the selected-token drawer or Search Intel token result THEN the same `TokenProfileCard` SHALL show available official links and description without requiring a narrative agent run.
- **AC9**. WHEN profile data is not ready THEN UI SHALL show a compact missing/unsupported state and keep timeline, posts, score, and market content usable.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| GMGN rate limits profile refresh | Medium | Use due-selection, TTL, per-loop limit, and provider cache; errors update `next_refresh_at_ms`. |
| Profile data becomes stale | Medium | Store `observed_at_ms` and `next_refresh_at_ms`; read model exposes observed time. |
| API latency regresses | High | API reads only persisted `asset_profiles`; no provider calls in request path. |
| Frontend duplicates profile UI | Medium | Create one `TokenProfileCard` shared by drawer and Search Intel. |
| Narrative agent becomes a hidden dependency | High | Narrative is explicitly non-goal; profile card renders deterministic facts first. |
| Existing `enrichment_jobs` kills new job type | Medium | Do not use current social enrichment job table for narrative jobs in this pass. |

## Evolution path

After deterministic profile facts are visible, add a separate token narrative lane:

```text
asset_profiles + 24h posts + market facts
  -> token_narrative_jobs
  -> Agents SDK structured output
  -> token_narratives
  -> optional "Generate Brief" action in Search/Profile UI
```

The future agent should reuse model-run audit patterns, but it should not reuse the current `enrichment_jobs` table until that table no longer retires non-social-event job types. The future narrative output should be optional, cached, and source-attributed. It should not replace official profile facts.

## Alternatives considered

- **Request-time GMGN calls from API**: rejected because it couples public latency and reliability to GMGN availability and makes Radar/Search failures harder to reason about.
- **Store profile inside `token_radar_rows.factor_snapshot_json`**: rejected because Radar rows are windowed scoring snapshots while profile is an asset-level slow-changing fact.
- **Frontend derives links from target fields**: rejected because target identity does not contain official links and provider-specific URL construction belongs server-side.
- **Use the existing social enrichment job table for token narrative now**: rejected because the current repository explicitly retires unknown job types.
- **Replace OKX discovery with GMGN**: rejected because profile hydration requires exact chain/address and does not solve symbol-only discovery.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Profile hydration starts from resolved DEX assets; provider calls live in `asset_market`; API reads persisted facts; Radar/Search share one profile contract; frontend shares one profile card. |
| Ask first | Adding website scraping, adding multi-provider profile reconciliation, replacing OKX discovery, running narrative generation automatically for every token. |
| Never | API/request-time provider calls, profile facts inside scoring snapshots, agent-generated text as official profile fact, frontend parsing provider raw payloads. |
