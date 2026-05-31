# Spec — Watchlist Page Single Source Hard Cut

**Status**: Implemented
**Date**: 2026-05-16
**Owner**: Codex / Qinghuan
**Related**: `docs/superpowers/plans/active/2026-05-16-watchlist-page-single-source-hard-cut-plan-cn.md`, `docs/superpowers/specs/active/2026-05-14-watchlist-handle-intel-cn.md`, `docs/superpowers/specs/active/2026-05-16-event-token-projection-unification-cn.md`, `docs/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`

## Background

`/watchlist?handle=...` is currently a mixed-source screen. The route shell builds `watchlistAccountCases` from `liveItems`, where `liveItems` is a merge of `/api/recent` replay and WebSocket events (`web/src/routes/AppRoutes.tsx:68-101`). `/api/recent` is capped at `limit=80` and uses the live route's `scope` and `handles` filters (`web/src/features/live/api/useLiveRecentQuery.ts:15-23`), whose default route state is `window=1h`, `scope=all`, and `handles=""` (`web/src/features/live/state/liveRouteState.ts:14-18`). This means the selected watchlist page's hero, evidence count, and right-side clusters are derived from a short global feed buffer, not from the selected handle's persisted timeline.

The same `WatchlistPage` already reads durable handle intelligence through React Query. It calls `useHandleSummaryQuery` and `useHandleTimelineQuery` with the selected handle and watchlist timeline scope (`web/src/features/watchlist/ui/WatchlistPage.tsx:35-47`). The backend endpoints exist under `/api/watchlist/handle/{handle}/summary` and `/api/watchlist/handle/{handle}/timeline` (`src/parallax/app/surfaces/api/http.py:132-186`). The read service returns summary status, staleness, pending recompute, signal counts, input counts, model, `summary_zh`, and topics (`src/parallax/domains/watchlist_intel/services/handle_summary_service.py:182-208`). The timeline repository reads `events` joined to `social_event_extractions`, filters `scope=signal` with `se.is_signal_event = TRUE`, and fills `token_resolutions` from the unified event-token projection (`src/parallax/domains/watchlist_intel/repositories/watchlist_intel_repository.py:376-440`).

The current UI does not treat those durable watchlist APIs as the page source of truth. `WatchlistPage` still renders `WatchlistHero`, `SignalStrip`, `ClusterPanel`, and `RiskPanel` from `selectedCase` props (`web/src/features/watchlist/ui/WatchlistPage.tsx:57-91`). Those props are built by `buildWatchlistAccountCases`, which filters the live buffer by author handle, slices recent evidence to 8 items, and derives token/narrative clusters from `event.cashtags`, `entities`, `token_intents`, and hashtags (`web/src/features/watchlist/model/watchlistCase.ts:43-85`). It does not consume `social_event.token_candidates` or the timeline's unified `token_resolutions`.

The event-token projection has a narrower semantic contract than LLM token candidates. `EventTokenProjectionQuery` returns only current resolved `Asset` or `CexToken` mentions with public identity and price payloads (`src/parallax/domains/token_intel/queries/event_token_projection_query.py:16-121`). By contrast, `social_event_extractions.token_candidates_json` can contain unresolved symbols, stock tickers, project names, and false-positive semantic candidates. The watchlist page currently labels its right rail as "Token mentions" but only reads live-buffer cashtags/intents, so it can show `Tokens 0` even when the handle timeline contains unresolved candidates in `social_event.token_candidates`.

The route parameter name `scope` is also overloaded. The live radar route owns `scope=all|matched` (`web/src/features/live/state/liveRouteState.ts:6-24`), while the watchlist route owns `scope=signal|all` (`web/src/features/watchlist/state/watchlistRouteState.ts:6-12`). Because the cockpit shell's controls use live route state on every shell route, a watchlist URL can share a parameter name with an incompatible enum.

Token Case uses a local hero return link: `<a href="/">返回</a>` (`web/src/shared/ui/case-file/TokenCaseHero.tsx:37-42`). Watchlist's hero has no equivalent back affordance (`web/src/features/watchlist/ui/WatchlistPage.tsx:98-129`). The two pages therefore do not share banner/action behavior even though both are drilldown pages inside the same cockpit shell.

Runtime evidence from the local service on 2026-05-16 confirms the split. `/api/watchlist/handle/marionawfal/timeline?scope=signal&limit=80` returned 42 signal events, 11 `social_event.token_candidates`, 3 cashtags, and 0 resolved `token_resolutions`; the page rendered the same handle with timeline rows but showed `Evidence 6`, `Tokens 0`, and `Narratives 0` because those cards came from the global live buffer.

## Problem

The Watchlist page presents contradictory facts because it mixes durable handle-level read models with a short global live buffer. Users cannot tell whether `Tokens 0` means "no token-like mentions", "no resolved crypto target", "not in the replay buffer", or "the page did not read the field". The `signal` default is semantically correct for the backend but unclear in the UI. The route parameter collision and inconsistent banner return behavior make the page feel bolted onto the cockpit rather than a first-class drilldown.

## First Principles

1. **One visible fact has one owner.** Watchlist handle facts must come from `domains/watchlist_intel` read services. The selected handle page must not reconstruct account facts from `/api/recent` or WebSocket replay.
2. **Resolved tokens and candidate mentions are different products.** `token_resolutions` means resolved public event-token projection. `social_event.token_candidates`, cashtags, and hashtags are evidence/candidate context. The UI must label them separately and must not collapse them into one `Tokens` count.
3. **Route state is feature-owned.** Watchlist timeline scope must not reuse the live radar `scope` URL key. A watchlist URL should be stable even when the cockpit shell owns radar controls.
4. **No compatibility layer.** The hard cut deletes the old account-case prop path, old watchlist live-buffer aggregation path, old `scope=signal|all` watchlist URL key, and old naked token-case anchor return. Runtime code must not contain fallback branches that revive them.
5. **Reuse existing projection contracts.** The fix must reuse `EventTokenProjectionQuery`, existing watchlist summary/timeline semantics, React Query, route-state helpers, `RemoteState`, `ObsidianPill`, and shared UI primitives. It must not duplicate token resolution SQL or frontend token extraction logic.

## Goals

- **G1 Single-source selected handle page.** Every selected-handle card, hero timestamp, insight rail cluster, timeline row, and empty state on `/watchlist` is derived from watchlist handle API responses, except notification unread counts, which remain owned by the notifications domain and must be labelled as notification state.
- **G2 Durable overview read model.** Add a watchlist handle overview API that derives source counts, signal counts, last event time, resolved token clusters, candidate mention clusters, narrative clusters, and data-quality notes from `events`, `social_event_extractions`, and the unified event-token projection. It must not create a new persisted table or background worker.
- **G3 Clear semantics.** The UI distinguishes resolved crypto targets from candidate mentions. `signal` is presented as structured signal events, not as a trading signal. `all` is presented as the source stream.
- **G4 Route isolation.** Watchlist uses a feature-specific URL key for timeline scope and no longer depends on the cockpit live route's `scope=all|matched`.
- **G5 Banner consistency.** Token Case and Watchlist use a shared route-return control with consistent label, accessible name, icon, styling, and client-side navigation semantics.
- **G6 Hard deletion.** Old `WatchlistAccountCase` page props, old selected-handle live-buffer derivation, old watchlist `scope` URL compatibility, and old token-case `<a href="/">返回</a>` are removed from runtime code and guarded by tests or architecture checks.
- **G7 Verification.** Backend, frontend, route, and browser checks prove that `marionawfal`-style data displays `candidate mentions > 0` while `resolved tokens = 0` without contradiction.

## Non-goals

- This work does not change `social_event_extractions.is_signal_event` model behavior or LLM extraction prompts.
- This work does not resolve stock tickers such as `$ALOY` into crypto `Asset` or `CexToken` targets.
- This work does not add new watchlist summary LLM jobs, tables, or workers.
- This work does not redesign the global cockpit side rail beyond removing its dependency on selected-page account-case props.
- This work does not change Signal Lab candidate decisions, Pulse Agent policy, or token-radar scoring.

## Target Architecture

The Watchlist feature has three server-state sources:

- **Handle list overview** for the cockpit watchlist rows: configured handles plus persisted last-seen/source/signal facts, merged in the frontend with notifications-owned unread counts.
- **Selected handle overview** for the selected page's hero, metric strip, resolved token clusters, candidate mention clusters, narrative clusters, and risk/data-quality notes.
- **Selected handle summary and timeline** for account-level topic summary and paginated source/signal events.

The selected Watchlist route no longer receives an `accountCases` prop. It receives only the API token, configured handles, and optional notification unread counts. The feature's API hooks own all watchlist server reads. The page component becomes a composition layer over focused components: route state, hero, metric strip, summary panel, timeline, and insight rail.

The backend keeps watchlist reads inside `domains/watchlist_intel`. Raw SQL remains in the watchlist repository. HTTP remains an app surface and calls domain read services. Token projection remains in `domains/token_intel/queries/event_token_projection_query.py`; watchlist overview/timeline delegate to it instead of duplicating token identity joins.

No compatibility code remains. Existing tests that reference the deleted account-case path are rewritten to assert the new API-backed behavior. Old public URL `scope=signal` is not translated at runtime; the route defaults to the new key and ignores unknown watchlist-local params.

## Conceptual Data Flow

```text
events
  + social_event_extractions
  + EventTokenProjectionQuery
        ↓
WatchlistIntelRepository
        ↓
WatchlistHandleReadService
        ↓
HTTP /api/watchlist/handles/overview
HTTP /api/watchlist/handle/{handle}/overview
HTTP /api/watchlist/handle/{handle}/summary
HTTP /api/watchlist/handle/{handle}/timeline
        ↓
features/watchlist/api React Query hooks
        ↓
WatchlistPage route state + view models
        ↓
Hero / MetricStrip / Summary / Timeline / InsightRail
```

The only frontend merge is notifications unread counts with handle rows. That merge is allowed because notifications are a separate domain fact, not a source-event fact.

## Core Models

### Watchlist Handle Row Overview

Represents one configured handle in the cockpit watchlist rail.

- `handle`: normalized configured handle.
- `last_source_event_at_ms`: latest persisted source event timestamp for that handle, nullable.
- `recent_source_event_count`: count inside the overview window.
- `recent_signal_event_count`: signal count inside the overview window.
- `total_signal_event_count`: all-time persisted signal count.
- `summary_status`: latest summary status if present.
- `summary_is_stale`: whether the current summary is stale.

### Watchlist Handle Overview

Represents selected-handle page facts.

- `handle`.
- `window`: overview window semantics used for counts and clusters.
- `scope`: `signal` or `all`, matching selected timeline scope.
- `last_source_event_at_ms`.
- `source_event_count`.
- `signal_event_count`.
- `resolved_token_count`.
- `candidate_mention_count`.
- `narrative_count`.
- `resolved_token_clusters`: clusters derived only from unified `token_resolutions`.
- `candidate_mention_clusters`: clusters derived from `social_event.token_candidates` and event cashtags that are not resolved targets.
- `narrative_clusters`: hashtags and high-confidence anchor terms that are not token-like.
- `risk_notes`: deterministic notes such as "candidate mentions are unresolved", "summary stale", or "structured extraction missing for all-scope rows".

### Watchlist Timeline Scope

- `signal`: rows with `social_event_extractions.is_signal_event = TRUE`.
- `all`: source events for the handle, with nullable `social_event`.

The UI label should make clear that `signal` is a structured social-event filter. It is not a trading recommendation and not a Signal Lab decision.

## Interface Contracts

### `GET /api/watchlist/handles/overview`

Authenticated endpoint. Returns rows for configured handles only. It does not accept arbitrary handles. It may accept an overview window parameter, but the default must be stable and documented. Unknown or invalid window values return a structured bad request. Rows are ordered by server-side persisted recency; the frontend may secondarily order by notification unread count.

### `GET /api/watchlist/handle/{handle}/overview`

Authenticated endpoint. `{handle}` is normalized with the same handle rules as existing watchlist endpoints. Unconfigured handles return `404 handle_not_found`. The endpoint accepts `scope=signal|all` and an overview window. It returns selected-handle overview facts and clusters. It does not call providers and does not write state.

### Existing Summary Endpoint

`GET /api/watchlist/handle/{handle}/summary` remains the topic-summary source. Its stale and pending fields are displayed directly; the frontend does not infer summary freshness from timeline rows.

### Existing Timeline Endpoint

`GET /api/watchlist/handle/{handle}/timeline` remains the paginated event stream. The frontend route parameter for timeline scope changes, but the API keeps the existing `scope=signal|all` query parameter because this is already a domain-local endpoint and not the URL route state.

### Frontend Route

`/watchlist?handle=<handle>&timeline_scope=signal|all` is the canonical shareable route. The selected handle defaults to the first configured handle when no handle is present. The selected timeline scope defaults to `signal`.

## Acceptance Criteria

- **AC1.** WHEN `/watchlist?handle=marionawfal&timeline_scope=signal` is opened and the backend has signal events with unresolved candidates but no resolved token projection, THEN the page SHALL show non-zero candidate mentions and zero resolved tokens with distinct labels.
- **AC2.** WHEN selected handle facts exist outside the `/api/recent` replay buffer, THEN the Watchlist page SHALL still show correct persisted last-seen, counts, clusters, summary, and timeline rows.
- **AC3.** WHEN the WebSocket has no event replay for the selected handle, THEN selected-handle Watchlist cards SHALL not regress to empty live-buffer values.
- **AC4.** WHEN the user switches timeline scope, THEN the URL SHALL use `timeline_scope` and the selected-handle overview and timeline SHALL refetch for the new scope.
- **AC5.** WHEN a live radar shell control writes `scope=all|matched`, THEN the Watchlist route SHALL not interpret that parameter as watchlist timeline scope.
- **AC6.** WHEN Token Case and Watchlist render their hero banners, THEN both SHALL use the shared route-return control without requiring a React Router provider.
- **AC7.** WHEN code is searched for the deleted compatibility path, THEN runtime code SHALL contain no `accountCases` prop on `WatchlistPage`, no `buildWatchlistAccountCases` selected-page path, and no watchlist-local `scope=signal|all` route-state reader.
- **AC8.** WHEN `/api/watchlist/handle/{handle}/overview` is called for an unknown handle, THEN the API SHALL return `404 handle_not_found`.
- **AC9.** WHEN the overview endpoint aggregates token facts, THEN it SHALL reuse the unified public event-token projection and SHALL not expose internal resolution audit fields.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Overview queries become expensive on high-volume handles. | Medium | Keep overview window bounded by default, use existing handle/time index, and test query shape with seeded integration data. |
| Candidate mentions are mistaken for tradeable tokens. | High | Separate labels and counts: `Resolved targets` vs `Candidate mentions`; candidate links go to search, not token-case unless resolved. |
| Deleting old account-case props breaks sidebar rows. | Medium | Add handle-list overview endpoint and rewrite sidebar row model to use server rows plus notification unread counts. |
| Route param hard cut breaks old shared links with `scope=signal`. | Low | Deliberate hard cut. Unknown `scope` is ignored; default `timeline_scope=signal` produces a valid page. No runtime translator. |
| Frontend duplicates aggregation logic already in backend. | Medium | Backend owns clusters. Frontend model only maps response shape to display labels. |
| Shared back control becomes too generic. | Low | Keep it narrow: a route return link component, not a page-header framework. |

## Evolution Path

After this hard cut, Watchlist can evolve toward account-level trend history and cross-handle comparison. The important constraint is not to turn the Watchlist page into another token-scoring surface. It should remain a source-monitoring surface that explains what an account is posting, what structured signals were extracted, and which token-like mentions are resolved versus unresolved.

Future expansions can add:

- per-handle topic history from `watchlist_handle_summary_runs`;
- a language/gate diagnostic panel for extraction coverage;
- deep links from candidate mentions to Search Inspect;
- a handle-level "why stale" operational panel.

These should build on the same watchlist overview/read-service boundary.

## Alternatives Considered

- **Frontend-only aggregation from timeline pages** — rejected because the loaded page is not the selected handle's total window, pagination makes counts unstable, and frontend aggregation would duplicate backend token/candidate semantics.
- **Keep `accountCases` as a fallback until overview lands** — rejected because it preserves the source split that caused the bug. This work is a hard cut.
- **Extend `/api/recent` with more handle-specific fields** — rejected because `/api/recent` is a global feed endpoint without cursor/handle overview semantics. It would couple the selected page to replay limits.
- **Persist a new watchlist overview table** — rejected because the overview is a deterministic read over existing facts and does not need a new writer, worker, or rebuild lifecycle.
- **Resolve LLM token candidates into assets in this change** — rejected because candidate resolution is a separate identity problem and would blur the distinction between extraction and resolved token projection.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Read selected-handle page facts from watchlist APIs; display resolved targets separately from candidate mentions; use `timeline_scope` in the Watchlist URL; reuse `EventTokenProjectionQuery`; use shared route-return control on Token Case and Watchlist. |
| Ask first | Changing summary LLM prompts, adding new persisted read models, changing Signal Lab decision semantics, changing token identity resolution policy. |
| Never | Reconstruct selected-handle page facts from `/api/recent` or WebSocket replay; keep `accountCases` as a Watchlist page prop; translate old `scope=signal|all` watchlist route params; duplicate token projection SQL in frontend or API surface; label unresolved candidates as resolved tokens. |
