# Kappa/CQRS Worker and PostgreSQL Audit - 2026-06-12

This is a static architecture and code audit of the current Parallax Kappa/CQRS runtime, worker set, backend read paths, and PostgreSQL query/index posture.

## Findings

### P1 - `/stocks-radar` performs provider IO in the HTTP read path

Evidence:

- `src/parallax/app/surfaces/api/routes_radar.py:60` constructs `StocksRadarService` inside the request and passes `runtime.stock_quote_provider` at `routes_radar.py:63`.
- `src/parallax/domains/token_intel/read_models/stocks_radar_service.py:37` loads stock rows from PostgreSQL, then `_quote_snapshots()` calls `self.quote_provider.quote(symbol)` per symbol at `stocks_radar_service.py:79`.

Why this matters:

- Mature CQRS read paths should read from materialized state, not call external providers. This endpoint couples API latency, rate limits, and provider outages to serving.
- It is also inconsistent with the rest of the runtime, where provider IO is generally confined to workers and then persisted as facts/current projections.

Recommendation:

- Introduce a stock quote fact/current table, for example `stock_quote_ticks` plus `stock_quote_current`, and a quote poll/projection worker.
- Change `StocksRadarService` to read current quote rows only. If quote rows are absent or stale, return unavailable/stale state from the DB, not from a live provider call.

### P2 - `resolution_refresh` manifest classification drifts from implementation

Evidence:

- `src/parallax/app/runtime/worker_manifest.py:205` defines `resolution_refresh`.
- It is labeled `WorkerRuntimeConstraint.TARGET_SCOPED_EXPANSION` at `worker_manifest.py:210`.
- The same manifest declares `dirty_target_tables=("token_discovery_dirty_lookup_keys",)` at `worker_manifest.py:222`.
- Runtime behavior claims lookup-key queue rows from `repos.discovery.claim_due_lookup_keys(...)` at `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py:77`.

Why this matters:

- The implementation is a dirty target/lookup queue consumer, not broad target-scoped expansion.
- The queue ownership is correct, but the constraint label weakens manifest-as-architecture guarantees and can mislead future contract tests or worker inventory reviews.

Recommendation:

- Reclassify this worker as the dirty queue consumer shape used by the other bounded projection/fact workers.
- Update the manifest wording from `asset_identity_resolution backlog` toward the explicit `token_discovery_dirty_lookup_keys` contract.

### P2 - Old `run_resolution_refresh_once` helper keeps a mixed provider/DB path

Evidence:

- The scheduler runtime path is the good path: it claims with one worker session, closes/commits, fetches provider data outside the session, then opens a new session to persist. See `resolution_refresh_worker.py:75` through `resolution_refresh_worker.py:109`.
- The helper `run_resolution_refresh_once(...)` starts at `resolution_refresh_worker.py:208` and accepts an already-open `repos`.
- It claims and starts lookup state with that repo, then calls `_process_lookup(...)` at `resolution_refresh_worker.py:245`.
- `_process_dex_symbol_lookup(...)` calls `dex_discovery_market.search_tokens(...)` at `resolution_refresh_worker.py:512` and writes candidates through the same `repos` at `resolution_refresh_worker.py:526`.

Why this matters:

- This appears to be a non-scheduler/test/ops helper rather than the current runtime hot path, but it preserves the pre-hard-cut pattern that mixes provider IO and repository state in one call graph.
- It is exactly the kind of redundant compatibility path that can reintroduce old lifecycle bugs through tests or one-shot ops commands.

Recommendation:

- Delete this helper or make it delegate to `ResolutionRefreshWorker._run_refresh_once()` with an explicit `DbPoolBundle`.
- If tests still need a pure function, split provider fetch from persistence as the runtime path already does.

### P2 - Notification delivery stale-running cleanup can become an unbounded update

Evidence:

- `src/parallax/domains/notifications/repositories/notification_repository.py:638` runs:
  `UPDATE notification_deliveries ... WHERE status = 'running' AND updated_at_ms < %s AND attempt_count >= max_attempts`
  before each claim.
- The initial index is `(status, next_run_at_ms, created_at_ms)` at `src/parallax/platform/db/alembic/versions/20260506_0001_initial_postgresql.py:576`.
- The claim partial index covers only pending/failed deliveries at `src/parallax/platform/db/alembic/versions/20260506_0002_postgres_queue_claims.py:35`.
- There is no matching partial index for stale running deliveries by `(updated_at_ms, delivery_id) WHERE status = 'running'`.

Why this matters:

- The normal claim path is indexed, but stale terminalization is not batched and does not have a purpose-built running-stale index.
- As `notification_deliveries` grows, this can degrade the delivery worker and produce unnecessary lock/WAL pressure.

Recommendation:

- Add a partial stale-running index:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_deliveries_running_stale
  ON notification_deliveries(updated_at_ms, delivery_id)
  WHERE status = 'running';
```

- Batch stale terminalization through a `WITH expired AS (...) LIMIT ... FOR UPDATE SKIP LOCKED` update.

### P3 - Token Radar pruning runs in the publication hot path

Evidence:

- `TokenRadarProjectionService.refresh_rank_set(...)` computes retention and prunes on every publish attempt at `src/parallax/domains/token_intel/services/token_radar_projection.py:506`.
- It calls `prune_target_features(...)` at `token_radar_projection.py:508` and `prune_edges(...)` at `token_radar_projection.py:517`.
- The deletes are direct range deletes in `src/parallax/domains/token_intel/repositories/token_radar_repository.py:589` and `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:162`.
- There are supporting indexes, including `idx_token_radar_target_features_window_freshness` and `idx_token_radar_rank_source_events_watched`, so this is not an immediate missing-index bug.

Why this matters:

- The shape is indexed, but repeated deletes inside a hot publication cycle can still cause WAL churn, vacuum churn, and p99 tail latency when source edges grow.

Recommendation:

- Move retention deletes to a maintenance worker or batch them with row limits.
- Keep publication focused on ranking, current-row upsert, and publication-state bookkeeping.

### P3 - Pulse read filters rely on JSONB expansion and non-trigram substring search

Evidence:

- `src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:58` uses `%q%` `ILIKE` over `candidate.symbol`, `candidate.subject_key`, and `candidate.target_id`.
- `_candidate_handle_filter_clause(...)` lower-cases `candidate.subject_key` and expands `source_event_ids_json || evidence_event_ids_json` through `jsonb_array_elements_text(...)` at `pulse_read_repository.py:296` through `pulse_read_repository.py:323`.
- Current migrations provide latest/target/subject/product indexes for `pulse_candidates`, but no trigram index for the `ILIKE` fields and no normalized candidate-event edge table for handle filtering.

Why this matters:

- Window/scope/display filters keep the common list path bounded, but handle and substring filters can become expensive once candidate histories grow.

Recommendation:

- Add a normalized `pulse_candidate_event_edges(candidate_id, event_id, author_handle)` projection or a compact author edge table.
- Add a functional index on `lower(subject_key)` if handle filtering remains direct.
- Add trigram indexes only if the `%q%` search is a real UI workflow; otherwise keep the endpoint narrow.

### P3 - Queue health aggregation uses broad OR predicates

Evidence:

- `src/parallax/app/runtime/queue_health.py:299` counts dirty target health with `COUNT(*) FILTER (...)`.
- It scans rows where `due_at_ms <= now OR leased_until_ms > now OR last_error IS NOT NULL` at `queue_health.py:317`.
- The function is cached with `QUEUE_HEALTH_CACHE_TTL_MS = 5000` at `queue_health.py:107`, and this is an ops/status path rather than a worker claim path.

Why this matters:

- This is acceptable today because it is cached and not on the projection hot path.
- If queue tables become very large, OR predicates plus aggregate filters can become a status endpoint cost center.

Recommendation:

- Split health into separate indexed counts per category or add partial error indexes for high-churn queues.
- Keep the cache and make status callers tolerate partial/unavailable health.

## Positive Architecture Findings

The core Parallax design is close to a mature Kappa/CQRS implementation:

| Kappa/CQRS principle | Current Parallax posture |
| --- | --- |
| Immutable/material facts are the source of truth | PostgreSQL fact tables such as `events`, `token_intents`, `token_intent_resolutions`, `asset_identity_*`, `market_ticks`, and `enriched_events` remain the business truth. Provider raw frames are not serving truth. |
| Read models are derived and rebuildable | Current read models use projection workers and dirty target queues. The manifest owns writer identity through `read_model_writer_by_table()` at `src/parallax/app/runtime/worker_manifest.py:704`. |
| Single writer per read model | Manifest validation fails on duplicate read model writers at `worker_manifest.py:704` through `worker_manifest.py:714`; architecture tests cover this. |
| Stable product/window identity | Token Radar, Macro, News, Pulse, CEX, and asset current models use target/window/product identities rather than run IDs as serving identity. Run IDs remain ledger metadata for agent side effects. |
| Idempotent writes | Current projections use natural keys, payload hashes, `IS DISTINCT FROM`, or stable publication state. Unchanged Token Radar publication writes zero current rows. |
| Wakeups are hints, not truth | Worker base waits on wake hints with bounded interval catch-up. Workers re-read PostgreSQL state after wake. |
| Provider IO stays outside DB transactions | Most workers claim in one short transaction, perform provider calls outside DB sessions, then persist in a fresh short transaction. Exceptions are listed in findings. |
| Backpressure and retries are durable | Dirty target/status queues use leases, retry state, advisory locks, and `FOR UPDATE SKIP LOCKED` claim patterns. |

## Writer and Read Model Map

Current read model ownership from the worker manifest:

| Worker | Read model tables | Queue/control input |
| --- | --- | --- |
| `market_tick_current_projection` | `market_tick_current` | `market_tick_current_dirty_targets` |
| `token_capture_tier` | `token_capture_tier` | `token_capture_tier_dirty_targets` |
| `token_profile_current` | `token_profile_current` | `token_profile_current_dirty_targets` |
| `token_radar_projection` | `token_radar_rank_source_events`, `token_radar_target_features`, `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_first_seen`, `projection_offsets`, `token_score_evaluations` | `token_radar_source_dirty_events`, `token_radar_dirty_targets` |
| `narrative_admission` | `narrative_admissions` | `narrative_admission_dirty_targets` |
| `news_item_brief` | `news_item_agent_briefs` | `news_projection_dirty_targets` filtered to `brief_input` |
| `news_page_projection` | `news_page_rows` | `news_projection_dirty_targets` filtered to `page` |
| `news_source_quality_projection` | `news_source_quality_rows` | `news_projection_dirty_targets` filtered to `source_quality` |
| `cex_oi_radar_board` | `cex_oi_radar_publication_state`, `cex_oi_radar_rows`, `cex_detail_snapshots` | fixed provider schedule |
| `macro_view_projection` | `macro_observation_series_rows`, `macro_observation_series_publication_state`, `macro_view_snapshots` | `macro_projection_dirty_targets` |
| `macro_daily_brief_projection` | `macro_daily_briefs` | latest macro snapshot |
| `pulse_candidate` | `pulse_candidate_edge_state`, `pulse_candidates`, `pulse_playbook_snapshots` | `pulse_trigger_dirty_targets`, `pulse_agent_jobs` |

## Backend Read Path Assessment

Pure DB/read-model paths:

- Token Radar reads `token_radar_current_rows`, profile current rows, and narrative admissions.
- News list/detail reads `news_page_rows` and related current projections.
- Macro reads `macro_view_snapshots`, `macro_observation_series_rows`, and `macro_daily_briefs`.
- CEX reads current board/detail snapshots.
- Pulse reads `pulse_candidates` and related job/run state.
- Search reads events and token target facts with bounded limits.
- Ops/status routes read worker and queue state; repair operations remain explicit CLI/ops workflows.

Exception:

- `/stocks-radar` performs live quote provider calls from the read service and should be moved behind a worker-owned current read model.

## PostgreSQL Performance Posture

Good patterns found:

- Dirty queues use stable primary keys, leases, due times, retry fields, and `FOR UPDATE SKIP LOCKED` claim patterns.
- High-churn queue tables such as `market_tick_current_dirty_targets` set lower fillfactor and aggressive autovacuum/analyze settings at `20260524_0095_market_tick_current_dirty_targets.py:36`.
- `events.search_text` has a trigram GIN index at `20260512_0032_search_v2_hard_cut.py:30`; `events.search_tsv` has a generated tsvector GIN index at `20260512_0032_search_v2_hard_cut.py:27`.
- `news_page_rows.search_text` has a partial trigram GIN index at `20260606_0152_news_page_search_document.py:98`.
- Token Radar current serving has venue/window/scope/lane/rank and target uniqueness indexes; rank source edges have target/time and watched/time indexes.
- Worker pools set separate API/worker/lock/tool/wake pools and distinct statement timeout classes.

Performance risks to prioritize:

1. Add stale-running notification delivery index and batch terminalization.
2. Move Token Radar retention deletes out of the publish path or batch them.
3. Normalize Pulse candidate-event author edges if handle filtering is user-facing.
4. Split queue health OR aggregates if status endpoints become slow under large backlogs.

## Redundant Compatibility Code Check

Likely cleanup:

- `run_resolution_refresh_once(...)` is the clearest redundant old path. The class runtime already has the safer session/provider/persist split.

Not classified as redundant compatibility:

- CLI `ops_*_repair` commands are explicit operator actions, not serving-path fallback.
- Agent output normalization repairs in Pulse are trust-boundary guardrails for LLM output, not legacy DB compatibility.
- News item brief reuse of fresh completed/failed runs appears to be cost and duplicate-work control, not API fallback. Keep it, but document retention and freshness rules if it continues to grow.

## Verification

Commands run:

```bash
uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py tests/architecture/test_token_radar_publication_state_hard_cut.py tests/architecture/test_macro_no_compatibility_contract.py
```

Result: `199 passed in 7.84s`.

```bash
uv run pytest tests/architecture/test_runtime_performance_architecture_hard_cut.py tests/architecture/test_projection_worker_idle_cost_contract.py tests/architecture/test_worker_manifest_static_contracts.py tests/architecture/test_token_radar_sql_surface_inventory_contract.py tests/architecture/test_equity_runtime_hard_delete_contract.py tests/architecture/test_runtime_lifecycle_hard_cut.py
```

Result: `67 passed in 0.62s`.

## Production Data Verification Gap

This audit did not connect to the operator-owned runtime config or production-sized PostgreSQL data:

- I did not run `uv run parallax config`.
- I did not run `EXPLAIN (ANALYZE, BUFFERS)` against live tables.
- I did not inspect `pg_stat_statements`, table bloat, autovacuum history, or real queue cardinalities.

The P2/P3 SQL items above are therefore code/schema risk findings, not measured production regressions. A follow-up production-data pass should first confirm `config_path` and `workers_config_path` point at `~/.parallax/`, then run redacted `EXPLAIN` and `pg_stat_statements` checks for the listed query shapes.
