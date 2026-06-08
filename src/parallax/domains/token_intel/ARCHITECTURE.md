# Token Intel Architecture

> **Scope.** Owns the Token Radar and token-identity map for cold-start agent
> work. Global package boundaries live in `../../../../docs/ARCHITECTURE.md`;
> public API / WebSocket / CLI contracts live in `../../../../docs/CONTRACTS.md`.

Token Radar is a mature, persisted pipeline. It is not "regex in the UI" and it
is not rebuilt from API payloads. The production chain is:

```
GMGN frame
  → CollectorService.handle_frame
  → normalize_gmgn_payload
  → IngestService.ingest_event transaction
      → events + event_entities
      → token_evidence
      → token_intents + token_intent_lookup_keys
      → token_intent_resolutions
      → registry_assets + asset_identity_evidence/current
      → enriched_events + inline market_ticks
      → event_anchor_backfill_jobs for short-lived missing-anchor control
  → TokenCaptureTierWorker ranks active market targets
  → MarketTickStreamWorker / MarketTickPollWorker refresh hot market_ticks
  → LivePriceGateway fans out cache-only live market updates
  → TokenRadarProjectionWorker
      → token_radar_rank_source_events
      → token_radar_target_features
      → token_radar_current_rows.factor_snapshot_json
      → token_radar_publication_state
  → read models / Signal Pulse / notifications
  → HTTP / WebSocket / CLI / frontend
```

## Stage Map

| Stage | Code owner | Persisted facts | Invariant |
|-------|------------|-----------------|-----------|
| Upstream collection | `../ingestion/runtime/collector_service.py`, `../ingestion/services/normalizer.py` | raw frames, `events` | GMGN frames are normalized to `TwitterEvent` once. Token snapshots are identity-only (`chain` / `address` / `symbol`); embedded GMGN price fields are not normalized into token evidence. Public-stream coverage remains `public_stream`, not a full Twitter firehose. |
| Entity extraction | `../evidence/services/entity_extractor.py` | `event_entities` | Extracts span-aware CA, Solana, TON, cashtag, hashtag, mention, URL, and domain entities from primary and referenced tweet text. Only CA and cashtag become token evidence. |
| Evidence construction | `services/token_evidence_builder.py` | `token_evidence` | CA/address evidence is strong resolution evidence; cashtag evidence is medium symbol evidence; GMGN token payload evidence is strong provider evidence. Canonical asset display identity is selected later from asset identity evidence. |
| Intent construction | `services/token_intent_builder.py` | `token_intents`, evidence links | One event can produce multiple token intents. Local cashtag aliases may attach to a nearby CA; a free cashtag stays a symbol-only intent. |
| Deterministic resolution | `services/token_intent_resolver.py`, `services/deterministic_token_resolver.py` | `token_intent_resolutions`, `token_intent_lookup_keys` | Resolver outputs identity status and reason codes, not probabilistic guesses. CEX token matches win first; symbol-only confirmed US equities become `MarketInstrument`/`NON_CRYPTO` before DEX same-symbol assets; explicit chain+address wins through the address path as exact asset identity. |
| Asset identity ledger | `../asset_market/identity_evidence_policy.py`, `../asset_market/repositories/identity_evidence_repository.py` | `asset_identity_evidence`, `asset_identity_current` | Tweet CA mentions, GMGN payloads, OKX symbol candidates, and OKX exact address hits are separate evidence kinds. One deterministic policy selects current canonical symbol/name/confidence. |
| Discovery and reprocess | `../asset_market/runtime/resolution_refresh_worker.py`, `../asset_market/repositories/discovery_repository.py` | `token_discovery_dirty_lookup_keys`, `token_discovery_results`, `registry_assets`, `asset_identity_evidence/current` | Intent writes and reprocess paths enqueue NIL / AMBIGUOUS symbol and address lookup keys. The worker claims due queue rows, refreshes them through OKX DEX, then reprocesses affected intents. It does not scan recent facts to discover due lookups. Successful refresh wakes downstream fact readers; it does not inline Token Radar projection. |
| Asset profile facts | `../asset_market/runtime/asset_profile_refresh_worker.py`, `../asset_market/runtime/token_profile_current_worker.py`, `../asset_market/services/token_profile_current_projection.py`, `../asset_market/read_models/token_profile_read_model.py` | `asset_profiles`, `cex_token_profiles`, `token_profile_current` | GMGN OpenAPI, Binance Web3, and Binance CEX profile rows are source-cache facts. Public profile/icon facts come from `token_profile_current`, projected from persisted source caches plus GMGN stream exact snapshot and OKX DEX exact-address evidence. Profile facts are never resolver evidence, ranking factors, or `factor_snapshot_json` fields. API and frontend code do not call providers. |
| Market facts | `../asset_market/runtime/{token_capture_tier_worker.py,market_tick_stream_worker.py,market_tick_poll_worker.py,event_anchor_backfill_worker.py,live_price_gateway.py}`, `../asset_market/services/{event_market_capture.py,asset_market_sync.py}` | `cex_tokens`, `price_feeds`, `market_ticks`, `enriched_events`, `token_capture_tier`; `event_anchor_backfill_jobs` control state | Ingest writes inline event-adjacent market ticks or a pending event-anchor fact plus a short-lived backfill job. Capture-tier projection assigns active targets to stream, poll, or inline-only. Stream and poll workers refresh hot market ticks. Event-anchor backfill consumes jobs, not fact rows, and terminalizes anchors it cannot validly attach. LivePriceGateway may receive high-frequency provider frames, but it is cache-only and does not persist facts. |
| Event token projection | `queries/event_token_projection_query.py` | reads `token_intent_resolutions`, `asset_identity_current`, `cex_tokens`, `price_feeds`, `enriched_events`, `market_ticks` | HTTP recent, WebSocket replay/live payloads, and watchlist timelines expose token mentions through this read model. It returns a lean public token-resolution payload with `symbol` and standard message `price`; public surfaces do not serialize raw resolution fact rows. |
| Radar projection | `runtime/token_radar_projection_worker.py`, `services/token_radar_projection.py`, `scoring/factor_snapshot.py`, `scoring/cross_section_normalizer.py`, `scoring/factor_diagnostics.py`, `queries/token_radar_rank_source_query.py`, `repositories/token_radar_rank_source_repository.py` | `token_radar_dirty_targets`, `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows.factor_snapshot_json`, `token_radar_publication_state`, `token_score_evaluations`, `projection_runs`, `projection_offsets` | Projection claims durable due dirty targets, applies due gates, builds one content-stable generation per `(projection_version, window, scope)`, and atomically publishes `token_radar_current_rows` plus `token_radar_publication_state`. Runtime projection does not run a broad recent fact-window catch-up scan. `token_radar_dirty_targets` carries source, market, and repair dirty kinds; market-only work reuses existing source edges and refreshes latest market context plus scoring output. `token_radar_rank_source_events` stores a `source_payload_hash` no-op gate and is rebuildable projection input plus bounded lazy evidence/detail only. `token_radar_current_rows` is the only online leaderboard table; `token_radar_publication_state` is the only online readiness and last-failure state. `token_radar_target_features` is projection-private cache and is not an API, CLI, Pulse, notification, or repair read path. Retired history/audit/coverage tables do not participate in online service. Repair is explicit ops enqueue, not worker runtime scan. |
| Search read model | `read_models/search_service.py`, `queries/search_events_query.py`, `services/query_parser.py`, `services/search_aliases.py` | `events.search_tsv`, `token_intent_resolutions`, `cex_tokens`, `registry_assets`, `asset_identity_current` | Search resolves query intent against current production identity first, retrieves target / lexical / trigram route hits, fuses them into cursor pages, and never performs provider calls, extraction, resolution mutation, scoring projection, or legacy `assets / asset_aliases / asset_venues` identity reads. |

## Factor Snapshot Contract

`token_radar_current_rows.factor_snapshot_json` is the current Token Radar product
contract. It contains:

- `schema_version = "token_factor_snapshot_v3_social_attention"` — the only runtime
  snapshot version accepted by readers.
- `subject` — deterministic target identity selected by the resolver and asset
  identity ledger, plus target-market identity facts.
- `market` — public market context for the social signal. It contains
  `event_anchor`, `decision_latest`, and `readiness` response keys generated
  from `enriched_events` and `market_ticks`; those names are not internal market
  DB concepts or worker/runtime semantics. `event_anchor_backfill_jobs` is never
  part of the Token Radar input contract. Market remains context and gate input,
  not an alpha family.
- `gates` — deterministic blockers, risk reasons, high-alert eligibility, and
  maximum decision. Identity readiness, CEX native-market identity, DEX
  market-cap / liquidity / holder floors, and market freshness are gates or
  data-health facts; they are not alpha factors.
- `data_health` — identity, market, social, and alpha readiness.
- `families` — social attention families only: `social_heat`,
  `social_propagation`, `semantic_catalyst`, and `timing_risk`.
  `timing_risk.weight = 0.0`, so timing contributes risk/gate context without
  positive alpha.
- `normalization` — cohort definition, per-family ranks, alpha rank, and status.
- `composite` — raw alpha score, cross-section rank score, family scores, and
  recommended decision derived from alpha families plus gates.
- `provenance` — source event ids and computation time.

`token_radar_current_rows` stores `rank_score`, `quality_status`,
`degraded_reasons_json`, and `factor_snapshot_json`. Token Radar current runtime
explanation source is `factor_snapshot_json`.
The market block is the single product-facing market contract; public readers do
not reconstruct legacy top-level market fields or process-local live market
fallbacks. Legacy score-centered JSON fields, v1 snapshot fields, and old
current-market refresh snapshots are not runtime fallback sources. `profile`
comes from the asset-level `token_profile_current` read model and is intentionally
outside the scoring snapshot. Signal Lab Pulse decisions consume v3 factor
snapshots, the public `market.decision_latest` response key, and deterministic
gates.

Latest read models read `token_radar_current_rows`; diagnostics use
`token_score_evaluations` and v3 score-version keys to keep populations
comparable. Online readiness and last-failure semantics come only
from `token_radar_publication_state`: `fresh` requires a ready latest attempt,
product/window current rows, or an explicitly empty ready publication. A failed
latest attempt with prior current rows is `stale`; a failed latest attempt
without current rows is `failed`; missing state must not be reported as
`fresh`. `current_generation_id` remains attempt audit metadata, not an online
serving join key. `fresh`, `stale`, and `failed` describe publication
freshness, while row `quality_status` describes business credibility. A
degraded row can still be a useful `watch`, but `high_alert` requires market
quality and deterministic gates to pass.

Successful publication generation ids are content-stable over current-row
content. When a rebuild produces unchanged content, publication state refreshes
without deleting or inserting current rows. Timestamp-derived ids are reserved
for failed attempts before row build (`attempt:{...}:{computed_at_ms}`), not
successful generations.

`token_radar_rank_source_events` rows are stable source packets. They are
rewritten only when their normalized source payload hash changes. Latest market
context is a target-level scoring input loaded from current market facts during
projection; market-only dirty targets must not rehydrate or rewrite every
source edge just because a quote changed.

`token_radar_rank_source_events` may be queried for detail/evidence only when
bounded by a current row key and limit. `token_radar_target_features` is a
projection-private intermediate layer, not an online read API. Retired
history/audit/coverage tables are not current-serving or publication-state
sources.

## Identity Boundary

Current resolver output is:

```
EXACT / UNIQUE_BY_CONTEXT / AMBIGUOUS / NIL
```

The schema and specs reserve `PROJECT_ONLY` and `INVALID`, but agents should not
assume current production code emits them until `services/deterministic_token_resolver.py`
does. Resolution statuses are identity facts and must not be overloaded with
storage lifecycle values such as `demoted_search`.

Resolution history is represented by `record_status`, `is_current`, and
supersession fields. Runtime reads use the current resolution for the configured
resolver policy.

Canonical asset display identity is not stored on `registry_assets`.
`registry_assets` owns chain/address identity and lifecycle status only.
`asset_identity_evidence` stores claims, and `asset_identity_current` stores the
selected current symbol/name/confidence plus reason metadata. Tweet mentions are
mention context; they do not become target identity when stronger exact provider
evidence exists. If an asset has no selected current identity, a resolved target
symbol remains `None` rather than falling back to the mention symbol.

## Hard Boundaries

- API, WebSocket, CLI, and frontend surfaces read projected rows or read models;
  they never perform entity extraction, token resolution, provider calls,
  scoring, SQL joins, or notification decisions.
- Token profile provider calls live only in `asset_market` refresh/ops paths.
  Search, Token Radar, and UI surfaces consume `TokenProfileReadModel` output
  from `token_profile_current`.
- LLM enrichment may label watched social events, but token identity resolution
  stays deterministic and does not call an LLM in the hot path.
- A symbol is a recall key, not identity. A chain+address or CEX registry fact
  is identity.
- DEX symbol discovery may add retained candidates, but it must not unboundedly
  expand `registry_assets`.
- Price freshness is market data health. It must not invent a new identity
  status or erase an otherwise valid deterministic identity decision.
- Market data health, duplicate clean state, and `social_signal_start_ms` do not
  create positive alpha. Duplicate concentration can penalize diffusion quality;
  clean duplication only removes that penalty.
- Token Radar target display uses current identity. Intent display symbol is
  preserved separately as what the tweet mentioned.
- Signal Pulse reads v3 `factor_snapshot_json`, first-class `decision_*`
  columns, `decision_json`, and deterministic gate output. Product decisions
  must not fall back to legacy Signal Pulse thesis, radar-score, or
  market-context JSON payloads.
- Token Radar online consumers read `token_radar_current_rows` plus
  `token_radar_publication_state` only. Failed publications must surface
  `stale` or `failed`; they must never be wrapped as `fresh` because older
  current rows still exist.

## Update Triggers

Update this file in the same change when any of these move:

- entity extraction inputs that affect token evidence;
- token evidence, intent construction, lookup key, or resolver policy;
- discovery admission, retained candidate, or reprocess behavior;
- market tick semantics used by Token Radar;
- projection windows, source query joins, factor families, gates, market
  freshness SLOs, evaluation horizons, or persisted radar row shape.
