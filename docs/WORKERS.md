# Workers

> **Scope.** Canonical cross-domain worker inventory and runtime
> ownership map. For a beginner-friendly flow, debugging guide, and
> layered state-machine explanation, read `WORKER_FLOW.md` first. Domain
> stage maps live in each domain's `ARCHITECTURE.md`; operational
> invariants live in `RELIABILITY.md`; package boundaries live in
> `ARCHITECTURE.md`.

This service is PostgreSQL-first. Workers do not pass business truth to
each other through in-memory messages. They persist facts or rebuild read
models, optionally emit a wake hint, and downstream workers re-read the
database.

## Runtime Contract

`src/parallax/app/runtime/worker_manifest.py` is the worker
contract source of truth. A worker exists only if its manifest entry exists;
the inventory below, `WorkersSettings`, worker factories, scheduler priority,
queue-depth ownership, `/readyz`, `/api/status`, and `ops worker-status` are
all checked against that manifest. `workers.yaml` is runtime knobs only: it may
set enabled state, cadence, leases, attempts, timeouts, wake hints, and agent
lane budgets, but it does not define the worker inventory.

Every long-running worker listed here is a `WorkerBase` subclass.
`runtime.bootstrap()` builds the process runtime:

```text
settings + WorkerManifest v1 + workers.yaml
  -> DBPoolBundle
  -> provider wiring
  -> domain worker factories
  -> canonical worker map
  -> WorkerScheduler
```

`WorkerScheduler` is the only runtime owner that starts, stops, closes,
and reports worker tasks. `WorkerBase` owns the common loop:

```text
run()
  -> optional advisory lock
  -> run_once()
  -> WorkerResult/status
  -> wait interval_seconds or wake hint
  -> backoff on failure
```

Correctness must not depend on `NOTIFY` delivery. Every listener has a
bounded `interval_seconds` loop from `workers.yaml`, but that loop must
claim durable queues or read bounded read models. It must not run broad
fact-table scans when the dirty queue is empty.

## Worker Best Practices

Use this checklist when adding or changing a worker. These rules are the
operational version of the Kappa/CQRS contract:

- Start from the manifest. A worker key, lane, kind, queue ownership, read
  model ownership, wake channels, and start priority are product architecture,
  not local implementation details. `workers.yaml` may tune runtime behavior,
  but it must not create aliases or hidden workers.
- Claim or reserve before doing expensive work. Dirty-target and job workers
  claim bounded rows first; LLM workers reserve agent capacity before claiming
  business targets. No-start backpressure does not burn attempts or write
  business run ledgers.
- Keep runtime loops proportional to changed targets. An idle worker should
  observe queue depth and return. It should not scan historical facts,
  read-model history, or provider history to discover work while idle.
- Keep provider IO outside DB sessions. Load the minimal input packet, close
  the worker session, call the provider/subprocess/filesystem/network, then
  persist the result in a new worker session.
- Make current read models compact and stable. Current rows are keyed by
  product/window/scope/target identity, not by run, generation, attempt,
  timestamp, or UUID ids. Publication state may describe freshness; it must
  not make old generations part of the serving identity. Unchanged projections
  write zero serving rows.
- Treat status as production code. `status_payload()`, custom
  `_queue_depth()` hooks, queue health, `/readyz`, `/api/status`, and
  `ops worker-status` are part of the runtime contract. Queue-depth hooks must
  be read-only and callable with no required arguments from
  `WorkerBase.status_payload()`.
- Test the concrete provider wrapper, not only fakes. If a worker depends on
  a provider protocol method, the runtime wrapper must implement that protocol
  directly and have a wiring test for the exact methods used.
- Keep public reads honest. API, WebSocket, CLI, and frontend paths read facts
  or read models and expose missing/degraded states. They do not run repair
  cleanup, call providers, resurrect removed aliases, or reconstruct old
  payload shapes.
- Hard-cut old runtime paths. Migrations, completed specs, and ops notes may
  mention history; runtime code must not keep fallback readers, dual writers,
  compatibility settings, or shadow queues for removed behavior.

## Truth Categories

Review workers by separating four categories:

| Category | Meaning | Examples | Rule |
|----------|---------|----------|------|
| Facts | Business observations and decisions that should be replayable | `events`, `token_intent_resolutions`, `asset_identity_evidence`, `asset_identity_current`, `market_ticks`, `enriched_events`, Pulse audit rows | Facts are product truth. |
| Read models | Rebuildable projections for reads and product workflows | `market_tick_current`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_first_seen`, `token_profile_current`, `pulse_candidates`, `watchlist_handle_signal_stats`, watchlist summaries | Exactly one runtime writer. |
| Control plane | Scheduling, retry, lease, budget, and queue state | `event_anchor_backfill_jobs`, `market_tick_current_dirty_targets`, `token_radar_dirty_targets`, `token_discovery_dirty_lookup_keys`, `macro_projection_dirty_targets`, projection dirty targets, `pulse_trigger_dirty_targets`, `narrative_admission_dirty_targets`, `discussion_digest_dirty_targets`, `token_profile_current_dirty_targets`, `token_image_source_dirty_targets`, `asset_profile_refresh_targets`, `token_capture_tier_dirty_targets`, `pulse_agent_jobs`, `notification_deliveries` | Never treat job state as product truth. |
| Cache/fan-out | Process-local convenience state | `LivePriceGateway` latest cache and WebSocket fan-out | Cache is presentation-only unless persisted as facts. |
| Local media mirrors | Rebuildable local copies of provider media | `token_image_assets` plus files under `cache/token-images` | Public image URLs must come from ready local rows, never provider URLs. |

The most common architecture bug is mixing these categories. For
example, a job queue row can explain why work has not finished, but it
cannot become the public market context for a token.

## Canonical Flow

The main chain is:

```text
collector
  -> IngestService transaction
  -> token_capture_tier
  -> market_tick_stream / market_tick_poll / event_anchor_backfill
  -> resolution_refresh and profile refresh lanes
  -> token_image_mirror
  -> token_radar_projection
  -> narrative_admission (only when narrative bulk analysis gate is enabled)
  -> mention_semantics / token_discussion_digest (same gate)
  -> macro_sync / macro_view_projection
  -> pulse_candidate / notifications / API / WebSocket / CLI
```

`IngestService` is not a long-running worker, but it is listed in this
document because every downstream worker depends on the facts it writes.
Macro Intel has a normal fact-ingest worker. `macro_sync` claims bounded
sync windows, runs the packaged `macrodata` executable outside DB
transactions, writes `macro_observations`, `macro_import_runs`, and
sync control/audit rows, then wakes projection as a hint. The
`macro import-bundle` CLI is offline replay/seed only.

Narrative bulk analysis is all-or-nothing at runtime. The gate requires
`narrative_admission`, `mention_semantics`, and `token_discussion_digest`
to be enabled and the shared LLM model config to be present. When any part
of that trio is disabled, Token Radar does not enqueue new
`narrative_admission_dirty_targets`, and the narrative worker factory keeps
the whole trio disabled. Existing rows remain inspectable operational state;
they do not gate News high-signal notifications or Signal Pulse.

## Worker Inventory

<!-- worker-inventory-keys:
collector, token_capture_tier, market_tick_stream, market_tick_poll, market_tick_current_projection,
event_anchor_backfill, live_price_gateway, resolution_refresh,
asset_profile_refresh, token_image_mirror, token_radar_projection, token_profile_current,
narrative_admission, mention_semantics, token_discussion_digest,
news_fetch, news_item_process,
news_item_brief, news_page_projection, news_source_quality_projection,
cex_oi_radar_board, macro_sync, macro_view_projection,
pulse_candidate, notification_rule,
notification_delivery
-->

| Worker | Owner | File | Reads | Writes | Wake-in | Wake-out | Catch-up |
|--------|-------|------|-------|--------|---------|----------|----------|
| `collector` (`CollectorService`) | `ingestion` | `domains/ingestion/runtime/collector_service.py` | GMGN public stream (WS) | none direct; calls `IngestService` per frame | provider-driven (WS) | none | continuous WS |
| `token_capture_tier` (`TokenCaptureTierWorker`) | `asset_market` | `domains/asset_market/runtime/token_capture_tier_worker.py` | due `token_capture_tier_dirty_targets`; bounded ranked live-market target set | `token_capture_tier` | poll | none | `interval_seconds` |
| `market_tick_stream` (`MarketTickStreamWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_stream_worker.py` | `token_capture_tier(tier=1)`, OKX DEX WS | `market_ticks(source_tier='tier1_ws')` | provider-driven (WS) | `market_tick_written` | bounded stream cycle |
| `market_tick_poll` (`MarketTickPollWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_poll_worker.py` | `token_capture_tier(tier=2)`, OKX DEX and Binance USD-M CEX REST quotes | `market_ticks(source_tier='tier2_poll')` | poll | `market_tick_written` | `interval_seconds` |
| `market_tick_current_projection` (`MarketTickCurrentProjectionWorker`) | `asset_market` | `domains/asset_market/runtime/market_tick_current_projection_worker.py` | due `market_tick_current_dirty_targets`, append-only `market_ticks` | `market_tick_current`, `token_radar_dirty_targets` for changed market current rows | `market_tick_written` | `market_tick_current_updated` after successful current changes | `interval_seconds` |
| `event_anchor_backfill` (`EventAnchorBackfillWorker`) | `asset_market` | `domains/asset_market/runtime/event_anchor_backfill_worker.py` | due `event_anchor_backfill_jobs`, event-adjacent `market_ticks`, quote providers inside the lag budget | `market_ticks`, narrow `enriched_events` lifecycle transition, `event_anchor_backfill_jobs` status | poll | `market_tick_written` | `interval_seconds` |
| `live_price_gateway` (`LivePriceGateway`) | `asset_market` | `domains/asset_market/runtime/live_price_gateway.py` | bounded live target rows from `token_capture_tier`, latest `market_ticks` per target | in-process latest cache and WebSocket fan-out only | poll | none | `interval_seconds` |
| `resolution_refresh` (`ResolutionRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/resolution_refresh_worker.py` | due `token_discovery_dirty_lookup_keys`, OKX DEX discovery | refreshed `token_intent_resolutions`, `registry_assets`, `asset_identity_evidence/current`, `token_discovery_results`, queue completion/reschedule state | poll | `resolution_updated` | `interval_seconds` |
| `asset_profile_refresh` (`AssetProfileRefreshWorker`) | `asset_market` | `domains/asset_market/runtime/asset_profile_refresh_worker.py` | due `asset_profile_refresh_targets`, configured DEX profile sources | `asset_profiles`, refresh target state, `token_profile_current_dirty_targets` when source facts change | poll | none | `interval_seconds` |
| `token_image_mirror` (`TokenImageMirrorWorker`) | `asset_market` | `domains/asset_market/runtime/token_image_mirror_worker.py` | due `token_image_source_dirty_targets` only; it does not scan source tables | `token_image_assets`, local cache files, `token_profile_current_dirty_targets` on terminal image changes | poll | none | `interval_seconds` |
| `token_radar_projection` (`TokenRadarProjectionWorker`) | `token_intel` | `domains/token_intel/runtime/token_radar_projection_worker.py` | `token_radar_dirty_targets`; compact `token_radar_rank_source_events` rank-source edges | `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_first_seen`, `projection_runs`, `projection_offsets`, `token_score_evaluations` | `market_tick_current_updated`, `resolution_updated` | `token_radar_updated` | `interval_seconds` |
| `token_profile_current` (`TokenProfileCurrentWorker`) | `asset_market` | `domains/asset_market/runtime/token_profile_current_worker.py` | due profile dirty targets; exact profile/evidence sources, full `token_image_assets` states, existing image dirty targets | `token_profile_current`, `token_image_source_dirty_targets` | poll | none | `interval_seconds` |
| `narrative_admission` (`NarrativeAdmissionWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/narrative_admission_worker.py` | due `narrative_admission_dirty_targets`; target-scoped Radar rows, `events`, current `token_intent_resolutions` | `narrative_admissions`, `discussion_digest_dirty_targets` | `token_radar_updated`, `resolution_updated` | none | `interval_seconds` |
| `mention_semantics` (`MentionSemanticsWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/mention_semantics_worker.py` | leased due `token_mention_semantics` rows and exact source events | `token_mention_semantics`, `narrative_model_runs`, `discussion_digest_dirty_targets` on semantic completion | `token_radar_updated`, `resolution_updated` | `narrative_semantics_updated` | `interval_seconds` |
| `token_discussion_digest` (`TokenDiscussionDigestWorker`) | `narrative_intel` | `domains/narrative_intel/runtime/token_discussion_digest_worker.py` | due `discussion_digest_dirty_targets`; exact `narrative_admissions`, `token_mention_semantics`, market/profile facts | `token_discussion_digests`, `narrative_model_runs`, digest dirty target backoff | `token_radar_updated`, `narrative_semantics_updated`, `market_tick_written` | none | `interval_seconds` |
| `news_fetch` (`NewsFetchWorker`) | `news_intel` | `domains/news_intel/runtime/news_fetch_worker.py` | configured `news_intel.sources` with source classification/policy, due `news_sources`, RSS/Atom/CryptoPanic feeds, OpenNews REST `/open/news_search` catch-up | `news_sources`, `news_fetch_runs`, `news_provider_items`, `news_items`; semantic page/source-refresh work | poll | `news_item_written` | `interval_seconds`; no agent admission |
| `news_item_process` (`NewsItemProcessWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_process_worker.py` | unprocessed `news_items`, token identity interfaces, bounded same-item/story admission context | `news_item_entities`, `news_token_mentions`, `news_fact_candidates`, `news_items.content_class/content_tags_json/content_classification_json`, `news_items.market_scope_json`, `news_items.story_identity_json`, `news_items.agent_admission_*`; semantic page work and optional item-brief work after market-wide agent admission | `news_item_written` | `news_item_processed` | `interval_seconds` |
| `news_item_brief` (`NewsItemBriefWorker`) | `news_intel` | `domains/news_intel/runtime/news_item_brief_worker.py` | semantic item-brief work; processed `news_items`, entity/token/fact rows, current brief state, and current `agent_admission` after reserving `news.item_brief` | `news_item_agent_runs`, `news_item_agent_briefs`, refreshed `news_items.agent_admission_*`; semantic page work | `news_item_processed` | `news_item_brief_updated` | `interval_seconds`; no-start backpressure claims nothing and writes no run ledger |
| `news_page_projection` (`NewsPageProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_page_projection_worker.py` | semantic page reprojection work; target-scoped `news_items`, `news_token_mentions`, `news_fact_candidates`, current brief state, and agent admission state | `news_page_rows` | `news_item_written`, `news_item_processed`, `news_item_brief_updated`, `news_page_dirty` | none | `interval_seconds` |
| `news_source_quality_projection` (`NewsSourceQualityProjectionWorker`) | `news_intel` | `domains/news_intel/runtime/news_source_quality_projection_worker.py` | semantic source-quality refresh/window work; target-scoped `news_sources`, `news_fetch_runs`, `news_items`, `news_token_mentions`, `news_fact_candidates`, `news_item_agent_briefs` by source/window | `news_source_quality_rows`, `news_sources.source_quality_status` | `news_item_written` | `news_page_dirty` only when compact source status changes | `interval_seconds`; windows are owned by worker settings |
| `cex_oi_radar_board` (`CexOiRadarBoardWorker`) | `cex_market_intel` | `domains/cex_market_intel/runtime/cex_oi_radar_board_worker.py` | Binance-backed `price_feeds`, Binance USD-M ticker/premium/OI history, bounded CoinGlass enrichment when available | `cex_oi_radar_rows`, `cex_oi_radar_publication_state`, `cex_detail_snapshots` | poll | none | `interval_seconds`; current board row ids are stable by provider/exchange/period/target |
| `macro_sync` (`MacroSyncWorker`) | `macro_intel` | `domains/macro_intel/runtime/macro_sync_worker.py` | due `macro_sync_windows`; packaged `macrodata` history bundle after claim | `macro_observations`, `macro_import_runs`, `macro_sync_windows`, `macro_sync_runs` | poll | `macro_observations_imported` | claims one bounded window; idle cycles do no provider IO and no broad fact scan |
| `macro_view_projection` (`MacroViewProjectionWorker`) | `macro_intel` | `domains/macro_intel/runtime/macro_view_projection_worker.py` | due `macro_projection_dirty_targets`; then exact `macro_observations` history and `macro_observation_series_rows` current projection | `macro_observation_series_rows`, `macro_view_snapshots`, `macro_observation_series_publication_state` | `macro_observations_imported` | none | `interval_seconds`; no dirty target means no broad fact scan; unchanged signatures write zero serving rows |
| `pulse_candidate` (`PulseCandidateWorker`) | `pulse_lab` | `domains/pulse_lab/runtime/pulse_candidate_worker.py` | due `pulse_trigger_dirty_targets`; exact Token Radar current row and evidence context for Pulse `1h`/`4h` horizons | read models: `pulse_candidate_edge_state`, `pulse_candidates`, `pulse_candidates.decision_*`, `pulse_candidates.decision_json`, `pulse_playbook_snapshots`; control/audit: `pulse_agent_jobs`, run-budget tables, `pulse_agent_runs`, `pulse_agent_run_steps`, runtime-version and eval tables | `token_radar_updated` | none | `interval_seconds` |
| `notification_rule` (`NotificationWorker`) | `notifications` | `domains/notifications/runtime/notification_worker.py` | notification rules, candidate rows | `notifications` facts and `notification_deliveries` control rows | poll | none | `interval_seconds` |
| `notification_delivery` (`NotificationDeliveryWorker`) | `notifications` | `domains/notifications/runtime/notification_delivery.py` | pending `notification_deliveries` | `notification_deliveries` side-effect/control ledger | poll | none | `interval_seconds` |

## News Provider Operations

News runtime provider support is intentionally smaller than the source
classification vocabulary. The supported provider types are `rss`, `atom`,
`json_feed`, `cryptopanic`, and `opennews`. OpenNews is REST-only inside
`news_fetch`: bounded `/open/news_search` pages catch up by source cursor,
persist provider observations, and merge article facts through deterministic
canonical identity. Public URLs admitted by `public_url_identity_policy` are
hard item identity; generic/homepage/live/feed/preview URLs remain raw/provider
evidence. OpenNews missing-link observations may attach through bounded
material title identity before falling back to provider article id. Short-lived
OpenNews WebSocket subscribe cycles, hybrid fetch mode, and WebSocket policy
keys are rejected rather than kept as compatibility paths.
`/api/news/sources/status` reports:

- `provider_capabilities.supported_provider_types`
- `provider_capabilities.configured_provider_types`
- `provider_capabilities.unsupported_configured_provider_types`
- `source_hygiene` warnings for unsupported providers, missing coverage tags,
  and degraded/failing source health

Safe operator checklist:

```bash
uv run parallax config
curl -sS -H "Authorization: Bearer $GMGN_API_TOKEN" \
  http://127.0.0.1:8765/api/news/sources/status | jq '.data.provider_capabilities'
```

Only report config paths and booleans from `parallax config`; never
copy provider credentials, cookies, tokens, proxy URLs, or API keys into logs or
docs. `parallax ops repair-news-duplicates-hard-cut` is a guarded ops repair for
historical duplicate facts and derived rows; it is not a runtime worker path and
must be run only after the News worker/lease/advisory-lock guard passes.
Staged provider waves are:

1. Enable `cryptopanic` when credentials exist, as aggregator/specialist media.
2. Enable `opennews` when `news_intel.opennews.api_token` exists and explicit
   `opennews://subscribe` sources are intentionally enabled. Production crypto
   news coverage is split by provider engine into `opennews-news`,
   `opennews-listing`, and `opennews-onchain`; do not mix OpenNews `market`
   engine rows into the News tape. Use only REST policy keys such as
   `engineTypes`, `hasCoin`, `coins`, `rest_limit`, `max_rest_pages`, and
   `rest_overlap_ms`; removed WebSocket keys such as `fetch_mode`, `wss_url`,
   `stream_timeout_seconds`, `max_messages`, and `connect_timeout_seconds`
   hard-fail configuration.
3. Add official regulator, exchange, protocol, and issuer RSS/manual API feeds.
4. Add OpenBB/macro/equity adapters only behind explicit ownership boundaries.
5. Add social/community/developer primary-item sources only behind a fresh
   spec; replies, comments, and threads are not a current News storage surface.

## Narrative Intel Hard-Cut Ownership

`narrative_admissions.source_event_ids_json` is the source-set truth for
Narrative Intelligence. Health, digest completeness, public currentness, and
semantics queue depth must expand admitted source sets first; existing
`token_mention_semantics` rows cannot define source volume by themselves. The
same event may count once per current admission/window/scope, but duplicate
semantic fingerprints for one admission-source row still count as one covered
source row.

Token Radar remains the scanner. `5m` admissions may exist so Radar and health
can explain the live frontier, but `TokenDiscussionDigestWorker` does not write
`token_discussion_digests` for `5m`. The digest lane supports `1h`, `4h`, and
`24h` only.

Writer ownership remains narrow: `NarrativeAdmissionWorker` writes
`narrative_admissions`, `MentionSemanticsWorker` writes
`token_mention_semantics`, and `TokenDiscussionDigestWorker` writes
`token_discussion_digests`. `ops rebuild-narrative-intel` has the only
maintenance writer exception: while it holds the narrative worker advisory
locks, it may run hard-cut cleanup that deletes obsolete queued/retryable/stale
semantics and marks suppressed current digests stale. Fingerprint mismatch does
not demote a ready digest by itself; public reads expose the last ready epoch as
`updating` or `stale` with explicit delta metadata. HTTP routes and normal
worker loops must not call that cleanup path.

This is a hard cut with no runtime compatibility. Removed settings, source-age
prune behavior, stale digest fallbacks, and old public digest reasons are not
kept as aliases. Public digest missing state is reported through
`discussion_digest.currentness.display_status`: `current`, `updating`, `stale`,
`not_ready`, `out_of_frontier`, or `unsupported_window`. LLM cycle backpressure
is reported as `llm_cycle_budget_exhausted` or `llm_failure_budget_exhausted`;
epoch-policy deferral is separate from provider capacity.

## Token Radar And Watchlist Maintenance Ownership

`TokenRadarProjectionWorker` is the only runtime writer for
`token_radar_current_rows`, `token_radar_publication_state`, and
`token_radar_target_first_seen`. Token Radar online serving is
`token_radar_current_rows` plus `token_radar_publication_state`. `fresh` is
allowed only when publication state is `ready` and served rows match
`current_generation_id`. Failed latest attempts serve previous rows as `stale`
or no rows as `failed`. The compact first-seen read model preserves
`listed_at_ms` while current rows stay small.
Token Radar has no runtime hard-reset command. Legacy derived-storage removal
belongs to migrations, and online repair is handled by the domain projection
path plus explicit Token Radar dirty-target enqueue.
`token_radar_dirty_targets` preserves independent source, market, and repair
dirty kinds. Source-dirty and repair work may rebuild source edges;
market-only work reuses stable `token_radar_rank_source_events` rows and
refreshes only latest market context plus scoring output. Source-edge writes
use content hashes, so unchanged source packets do not rewrite the source-edge
table or downstream current rows.

## IngestService Boundary

`IngestService` writes the first durable facts in a single transaction:
`events`, `event_entities`, `token_evidence`, `token_intents`,
`token_intent_lookup_keys`, `token_intent_resolutions`,
`registry_assets`, `asset_identity_evidence`,
`asset_identity_current`, `market_ticks`, and `enriched_events`.

Inline event capture writes Tier 3 `market_ticks(source_tier='tier3_inline')`
and matching `enriched_events`. When an event anchor cannot be attached
from a fresh existing tick, ingest writes an `enriched_events` pending
fact and enqueues `event_anchor_backfill_jobs` control-plane work.

`IngestService` is transactional. It is called by `collector`; it is not
a `WorkerBase` subclass and does not get a `workers.yaml` key.

## Market Capture Lanes

Market capture has several lanes by design. This does not violate the
single-writer rule because `market_ticks` is an append-only fact table,
not a read model.

- `token_capture_tier` writes the rebuildable control projection that
  assigns active targets to Tier 1 stream, Tier 2 poll, or Tier 3
  inline-only capture.
- `market_tick_stream` owns Tier 1 OKX DEX WebSocket capture. It accepts
  only `chain_token` targets from `token_capture_tier(tier=1)`.
- `market_tick_poll` owns Tier 2 REST capture for DEX and CEX targets.
  It is the steady-state REST quote worker.
- `market_tick_current_projection` is the single runtime writer for
  `market_tick_current`. It claims durable dirty targets, selects the
  latest append-only tick by `(observed_at_ms, received_at_ms, tick_id)`,
  and enqueues Token Radar market dirty work only when the visible
  current row changes.
- `event_anchor_backfill` owns short-lived event-anchor catch-up. It
  consumes `event_anchor_backfill_jobs`, attaches a persisted nearby tick
  first, calls providers only inside the configured lag budget, and then
  terminalizes work.
- `live_price_gateway` reads latest persisted `market_ticks` and fans out
  WebSocket updates. It does not call upstream price providers and never
  writes market facts.

## Worker Manifest Runtime Boundary

Worker manifests declare the durable contract: inputs, owned fact/control
tables, read-model identities, provider IO, wakes, and advisory locks. Runtime
code must follow those declarations directly; there is no partial runtime
contract object or constructor-time contract injection.

Claim-driven workers keep the order explicit in their own `run_once` flow:

```text
claim due control rows -> load bounded payload -> provider IO outside DB session -> persist terminal/result rows
```

Provider IO must happen outside DB sessions and transactions. Projection and
terminal writes use fresh worker sessions or transactions owned by the worker
that owns the manifest entry. Architecture tests verify manifest identities,
dirty-target ownership, provider-IO classification, and the absence of hidden
worker lifecycle allowlists.

## Wake Channels

| Channel | Emitter | Listener | Hint payload |
|---------|---------|----------|--------------|
| `market_tick_written` | `MarketTickStreamWorker`, `MarketTickPollWorker`, `EventAnchorBackfillWorker` | `MarketTickCurrentProjectionWorker` | `{target_type, target_id}` |
| `market_tick_current_updated` | `MarketTickCurrentProjectionWorker` | `TokenRadarProjectionWorker` | `{target_type, target_id}` |
| `resolution_updated` | `ResolutionRefreshWorker` | `TokenRadarProjectionWorker` | `{lookup_keys: [...]}` |
| `token_radar_updated` | `TokenRadarProjectionWorker` | `MentionSemanticsWorker`, `TokenDiscussionDigestWorker`, `PulseCandidateWorker` | `{window, scope}` |
| `narrative_semantics_updated` | `MentionSemanticsWorker` | `TokenDiscussionDigestWorker` | `{window, scope, target_count}` |
| `news_item_written` | `NewsFetchWorker` | `NewsItemProcessWorker`, `NewsPageProjectionWorker` | `{source_id, count}` |
| `news_item_processed` | `NewsItemProcessWorker` | `NewsItemBriefWorker`, `NewsPageProjectionWorker` | `{count}` |
| `news_item_brief_updated` | `NewsItemBriefWorker` | `NewsPageProjectionWorker` | `{count}` |
Wake payloads are hints only. Consumers re-read DB on wake and catch up
on their configured cadence. `DBPoolBundle` owns wake emission and
listener construction through `wake_emitter()` and `wake_listener()`.
Domain workers never call `pg_notify` directly.

Adding a wake channel requires all of these in one change:

- emitter call through `WakeBus`;
- listener `wakes_on` entry in `workers.yaml`;
- a bounded `interval_seconds` catch-up path;
- a row in this table;
- tests for missed-wake recovery when practical.

## Lifecycle And Supervision

- `WorkerBase` owns the common run loop, timeout/backoff handling,
  `run_once()` execution, advisory lock acquisition, status payloads,
  queue-depth hooks, pool-wait metrics, and close semantics.
- `runtime.bootstrap()` constructs `Runtime.workers` from `WorkerManifest v1`
  factory ownership and replaces unavailable or disabled workers with disabled
  `WorkerBase` placeholders so status payloads always contain the same
  keys.
- `WorkerScheduler.start()` starts enabled workers in manifest priority
  order. `WorkerScheduler.stop()` calls `stop()`, waits for tasks,
  cancels stragglers, calls `aclose()`, and closes the `DBPoolBundle`.
- Worker timeout settings are layered. `soft_timeout_seconds` is an
  overrun signal owned by `WorkerBase`; it records active task age and
  keeps waiting for the same `run_once()` task. `hard_timeout_seconds`
  is a cooperative cancellation boundary; the worker cancels, awaits
  cleanup, and only then may start another `run_once()`. Agent lane
  `timeout_seconds` is a provider execution boundary inside
  `AgentExecutionGateway`. `statement_timeout_seconds` is the final SQL
  guard for synchronous DB work.
- Wake waiters use a dedicated single-thread executor for PostgreSQL
  `LISTEN` waits and are closed through `WorkerBase.aclose()`. They do
  not share the event loop default executor with other `to_thread` work.
- WebSocket fan-out is presentation-only and bounded per client. A slow
  subscriber can be dropped, but it must not block worker publish paths
  or other subscribers.
- Non-continuous workers must have a finite `hard_timeout_seconds`.
  `collector` is the only zero-hard-timeout worker because it is a
  continuous stream lifecycle with its own snapshot gate and watchdog.
- `/readyz`, `/api/status`, and `ops worker-status` expose worker state
  under `workers` and lane aggregate state under `worker_lanes`. `workers`
  is keyed by manifest worker name; `worker_lanes` is keyed by manifest lane
  (`ingest`, `identity_market_fact`, `projection`, `agent`, `notification`,
  `maintenance_cache`). `collector.details` carries collector counters,
  including `snapshot_gate_outcomes`; `snapshot_gate` is a global health field
  copied from those counters.
- Queue observability is owned by `app.runtime.queue_health`. It reads only
  manifest-declared dirty target, job, delivery, and status queue tables and
  emits per-worker and per-lane `queue_health` with status, due/running/failed
  and blocked counts, oldest due/running ages, and max attempts. It is not a
  supervisor and does not mutate queue rows.
- Runtime knobs live in `~/.parallax/workers.yaml`. The
  application/provider config in `config.yaml` must not contain worker
  interval, batch, concurrency, lease, max-attempt, soft/hard timeout,
  advisory lock, or wake-channel settings.

## Agent Execution Plane

LLM-backed workers use one shared `AgentExecutionGateway` per process.
The gateway is an operational control plane only: it owns lane bulkheads,
request/result audit envelopes, timeout, circuit breaker, structured JSON
object execution, application-side validation, and ops status. It does
not claim domain jobs, write domain queues, or persist product read
models.

The low-level `LLMGateway` is transport-only. It owns redacted LiteLLM
configuration, shared model policy, and lifecycle cleanup. Concrete provider
calls live in `integrations/model_execution`; gateway objects do not construct
provider SDK clients or expose worker/stage execution limits.

Current lanes are configured under `workers.agent_runtime` in
`workers.yaml`. `agent_runtime.defaults.model` is the single global
agent model default; any lane can override `model` locally and otherwise
inherits that default. Current lanes are `pulse.pipeline`, `pulse.signal_analyst`,
`pulse.bear_case`, `pulse.risk_portfolio_judge`,
`narrative.mention_semantics`, `narrative.discussion_digest`,
and `news.item_brief`. News fact candidates are deterministic outputs of
`news_item_process`, not a separate LLM lane. Attempt-burning workers reserve
capacity before claiming DB work:

`agent_runtime.defaults.model` and lane `model` select the registered model
capability profile. The profile owns provider family, client-validation
retry count, and provider request options such as DeepSeek thinking-mode
disablement. Structured output has a single runtime path: provider JSON
object mode plus application-side Pydantic validation. Lane overrides may
set `provider_family` and `client_validation_retries` for an unregistered
or experimental model; they merge with the registered profile when the
model is known. Example DeepSeek lane override:

```yaml
agent_runtime:
  lanes:
    pulse.signal_analyst:
      model: deepseek-v4-flash
```

Repository defaults keep lane controls separate from the model choice: all
agent lanes inherit `agent_runtime.defaults.model` unless an operator
intentionally overrides a lane. The production default is DeepSeek:

```yaml
agent_runtime:
  defaults:
    model: deepseek-v4-flash
    provider_family: deepseek
  lanes:
    pulse.pipeline:
      priority: high
    pulse.signal_analyst:
      priority: high
    pulse.bear_case:
      priority: high
    pulse.risk_portfolio_judge:
      priority: high
```

- `pulse_candidate` reserves `pulse.pipeline` before `pulse_agent_jobs`
  claim. The pipeline reservation owns the parent global slot for the
  full decision run; child stages reuse that parent global slot and
  acquire only their stage lane bulkhead (`pulse.signal_analyst`,
  `pulse.bear_case`, or `pulse.risk_portfolio_judge`).
- Signal Pulse builds a domain-owned cost guard after evidence packet
  construction and before LLM execution. Evidence-hard-blocked jobs finish
  with deterministic audit only; duplicate terminal fingerprints reuse prior
  output; source-quality-hidden and non-public paths run Qwen research without
  DeepSeek; public trade/watch candidates run Qwen research plus the DeepSeek
  final judge.
- `news_item_brief` reserves `news.item_brief` before claiming a brief dirty
  target. No-start backpressure does not claim, burn attempts, or write an
  agent run ledger; provider-started validation failures write
  `execution_started=true`.
If reservation is denied, the worker records `agent_backpressure_*` in its
iteration notes and does not claim a job, so no-start backpressure does not
burn attempts or write business run ledgers. Batch LLM workers must reserve
explicit `rate_units` before claim and must cap the claim limit to the actual
`reservation.rate_units` returned by the gateway. A worker that can still
observe a provider no-start exception after claim must release/reschedule the
dirty row without writing a business run ledger and without counting it as a
provider attempt.

Lane `priority` is an operator-facing policy label used in diagnostics
and incident triage. It is not a strict scheduler; fairness still comes
from explicit global concurrency, lane bulkheads, RPM limits, and domain
queue cadence.

## Layered State Machines

Worker bugs often look confusing because several state machines are
visible at once:

- provider connection state describes upstream IO health;
- collector snapshot-gate counters describe frame completeness;
- fact lifecycle describes durable observations;
- control-plane job status describes scheduling and retries;
- projection status describes read-model freshness;
- business decision state describes product output and audit results.

These layers are allowed to coexist. They conflict only if one layer
tries to answer another layer's question. See `WORKER_FLOW.md` for the
full state-machine map and debugging playbook.

## Adding A Worker

When introducing a new worker, do all of the following in the same
change:

1. Implement the worker as a `WorkerBase` subclass with a canonical
   `name`, typed worker settings, injected `DBPoolBundle`, telemetry,
   and any narrow provider protocols it needs. Put business work in
   `run_once()`.
2. Add a `WorkerManifest` entry with lane, kind, class path, start priority,
   input/ordering contracts, write ownership, idempotency evidence, side-effect
   ledgers when applicable, queue-depth table when applicable, and wake
   channels. Add a matching `WorkersSettings` field and default `workers.yaml`
   block, then construct the worker in the owning domain factory under
   `app/runtime/worker_factories/`.
3. Add a row to this file's worker inventory.
4. Add or update the wake channels table here if the worker introduces a
   channel, and add its `wakes_on` list to `workers.yaml` when it listens
   for wake hints.
5. Document the worker in the owning domain's `ARCHITECTURE.md` stage
   map.
6. If the worker writes a new derived table, declare its lifecycle class
   (`current`, `private_cache`, `control_ledger`, or `audit_fact`) and name
   its single writer in `ARCHITECTURE.md`. Current read models must use stable
   product/window keys, not run/generation/attempt/timestamp/UUID identity, and
   unchanged projections must write zero serving rows.
7. Extend architecture guards so `WorkerBase`, `WorkerManifest`,
   `WorkersSettings`, the default `workers.yaml`, and this file's
   `worker-inventory-keys` marker stay in lockstep.

## Update Triggers

Update this file in the same change as any of:

- A new worker class or removal of an existing one.
- A worker gaining or losing a wake-in or wake-out channel.
- A change to a catch-up cadence default.
- A worker moving between domains.
- A new `NOTIFY` channel name or hint payload shape.
- A read model gaining a new runtime writer or losing its declared writer.
- A control-plane table becoming part of a worker's scheduling contract.
