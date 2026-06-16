# Architecture

> **Scope.** Owns Python-service package boundaries, dependency direction, and conceptual data flow for Parallax Market Research System. The runtime package, import path, and CLI are `parallax`. Frontend (`web/`) architecture lives in `FRONTEND.md`. Public interface contracts live in `CONTRACTS.md`.

Parallax is organised around domain packages, explicit integration adapters, platform infrastructure, and app surfaces. Boundaries are mechanically enforced by `tests/architecture/test_src_domain_architecture.py` and `tests/architecture/test_project_structure.py::test_project_uses_domain_package_src_layout`.

```
GMGN public stream
  → domains/ingestion           (raw frame normalisation, snapshot gate)
  → domains/evidence            (transactional facts: events, evidence, intents, resolutions, asset identity)
  → domains/asset_market        (market tick capture, capture-tier projection, profile refresh/current projection, discovery)
  → domains/token_intel         (Token Radar current-row publication, scoring, search read model)
  → domains/narrative_intel     (current source-set admissions and legacy narrative currentness reads)
  → domains/pulse_lab           (candidate gate, agent route, decision, audit ledger)
  → domains/watchlist_intel     (handle timeline read model and account topic summaries)
  → domains/news_intel          (configured news ingestion, news facts, item briefs, page read model)
  → domains/cex_market_intel    (centralized exchange derivative radar read models)
  → domains/macro_intel         (macro observation facts and regime view snapshots)
  → domains/notifications       (rules, delivery)
  → app/surfaces/api + app/surfaces/cli
```

Macro intelligence has a normal runtime fact-ingest lane. `macro_sync` claims
bounded date windows in PostgreSQL before provider IO, runs the packaged
`macrodata-cli` runtime from the installed image, and writes
`macro_observations`, `macro_import_runs`, `macro_sync_windows`, and
`macro_sync_runs`. The Docker image installs `macrodata-cli` from its pinned Git
source. Runtime uses the packaged `macrodata` executable when the console
script is healthy, or the installed Python package entrypoint when the script is
absent or stale; it must not use `uv run` or depend on a host-local checkout
path.

```text
macro_sync windows
  -> packaged macrodata bundle history macro-core
  -> macro_observations / macro_import_runs / macro_sync_runs
  -> wake macro_observations_imported
  -> macro_view_projection
  -> feature engine and regime state machine
  -> macro_regime_v4 in macro_view_snapshots
  -> wake macro_view_snapshot_updated
  -> macro_daily_brief_projection
  -> assets_today in macro_daily_briefs
  -> /api/macro
  -> web /macro
```

`macro import-bundle` remains an offline replay/seed tool for saved
macrodata envelopes; it is not the normal freshness path. `macro sync` is an
operator-triggered execution of the same sync service used by `macro_sync`.
`macro_regime_v4` readiness requires both latest coverage and required history
coverage; one-point history is projected as `partial` with structured gaps
rather than `ready`.

US Stocks radar is a PostgreSQL read-model endpoint for social attention around
confirmed US equity `MarketInstrument` rows. It does not call market data
providers during HTTP requests. The flow is:

```text
GMGN cashtag event
  -> token_intents / token_intent_resolutions
  -> MarketInstrument + CONFIRMED_US_EQUITY
  -> /api/stocks-radar social row query
  -> web /stocks
```

The response keeps a `quote` block for schema stability, but until a persisted
US equity quote read model exists it reports `quote.status = "unavailable"` and
`quote.error = "quote_read_model_unavailable"`.
The query keeps mention counts and latest evidence over the full requested
window, but bounds public `source_event_ids` provenance to the latest per-target
events inside PostgreSQL rather than returning an unbounded event-id array.

This repository is the system of record for agent work: if a production
decision changes, update the nearest architecture / contract / reliability
document in the same change. A fresh agent must not need chat history to know
where token identity is extracted, resolved, refreshed, scored, and served.

Worker runtime inventory is not inferred from `workers.yaml` or factory
registries. `WorkerManifest v1` (`app/runtime/worker_manifest.py`) is the only
source for worker existence, lane, kind, class path, start priority, queue-depth
ownership, idempotency evidence, side-effect ledger evidence, and wake
contracts. `workers.yaml` supplies runtime knobs for manifest workers only and
unknown worker keys fail startup.

## Architecture Invariants (Kappa/CQRS)

These eleven invariants govern how data flows through the service. Code that
violates them is wrong even if tests pass; tests that depend on a violation
are wrong too.

1. **Facts-first persistence.** `events`, `event_entities`, `token_evidence`,
   `token_intents`, `token_intent_lookup_keys`, `token_intent_resolutions`,
   `registry_assets`, `asset_identity_evidence`, `asset_identity_current`,
   `market_ticks`, `enriched_events`, `news_provider_items`, `news_items`,
   `news_item_entities`, `news_token_mentions`, `news_fact_candidates`,
   and `macro_observations` are
   the business fact tables. Control plane tables such as
   `event_anchor_backfill_jobs`, `pulse_trigger_dirty_targets`,
   `narrative_admission_dirty_targets`,
   `token_radar_source_dirty_events`, `token_radar_dirty_targets`,
   `token_profile_current_dirty_targets`, `token_image_source_dirty_targets`,
   `asset_profile_refresh_targets`, `token_capture_tier_dirty_targets`, and
   `news_fetch_runs` own worker scheduling state and are not product truth.
   `news_projection_dirty_targets` is News Intel scheduling state for semantic
   page reprojection, item brief, and source-quality refresh/window work; it is
   not a public News fact.
   `macro_import_runs`, `macro_sync_windows`, `macro_sync_runs`,
   `macro_projection_dirty_targets`, and notification delivery rows record
   importer/sync, projection scheduling, delivery retry, or external-delivery
   reactivation control state; macro product state still rebuilds from
   `macro_observations`. Every derived read model can be rebuilt from the
   durable facts. Token fact writes for `token_evidence`, `token_intents`,
   `token_intent_lookup_keys`, and `token_intent_resolutions` require
   PostgreSQL mutation evidence before facts are returned or rewrite accounting
   advances: required upserts use `RETURNING *` with rowcount=1,
   `ON CONFLICT DO NOTHING` evidence links allow only rowcount 0/1, lookup
   replacement deletes require real non-negative rowcount, and resolution
   supersede updates must affect exactly one current row. Fallback `SELECT`
   readback is not write success evidence.
   App-runtime queue descriptors are read-only ops metadata for queue/status
   summaries; `app/runtime/job_queue.py` must not own generic claim, finalize,
   retry, lease, or stale-running lifecycle SQL for domain control-plane tables.
   Notification delivery retry budgets are owned by
   `settings.workers.notification_delivery`; `notification_rule` receives that
   policy through runtime factory wiring when it creates external delivery
   control rows.
   Existing notification fact aggregation is a serving-fact mutation, not a
   readback convenience path: `UPDATE notifications` must report `rowcount=1`
   before `NotificationInsertOutcome.aggregated` or external-delivery requeue
   state can advance.
2. **Append-only market tick facts.** Market data from any provider is
   normalised into `MarketTick`
   (`domains/asset_market/types/market_tick.py`) before persistence.
   `market_ticks` are append-only provider tick facts; provider raw frames
   are inputs, not facts. Market tick `INSERT ... DO NOTHING RETURNING`
   fact writes require PostgreSQL cursor rowcount evidence: rowcount=1 with a
   returned `tick_id` is a new fact, rowcount=0 with no row is the only valid
   dedupe conflict, and malformed rowcount/row mismatches fail before insert
   counts or wake decisions are reported.
3. **Event projections are committed with events.** `enriched_events` rows
   are event projection rows committed in the same ingest transaction as
   `events`. Inline ingest capture writes Tier 3 `market_ticks` and the
   corresponding enriched event rows; when an event anchor is missing, ingest
   enqueues a short-lived `event_anchor_backfill_jobs` control-plane row whose
   active lifetime comes from `settings.workers.event_anchor_backfill.active_window_ms`.
   Event-anchor job `UPDATE ... RETURNING` state transitions require
   PostgreSQL rowcount evidence matching returned rows before claims, terminal
   ledgers, retry rows, reconcile counts, or done/reschedule booleans are
   reported.
   Downstream readers do not reconstruct event market context from provider
   frames or worker job state.
4. **Public event token mentions are projections.** HTTP recent, WebSocket
   replay/live event payloads, and watchlist timelines read token mentions
   through the shared event-token projection over `token_intent_resolutions`,
   identity tables, `enriched_events`, and `market_ticks`. Public payloads do
   not return raw resolution fact rows. Selected current resolution rows must
   expose non-empty resolution/intent/event/status fields plus list-shaped
   `reason_codes_json`, `candidate_ids_json`, and `lookup_keys_json`; malformed
   rows fail at the projection boundary instead of being repaired into empty
   strings or arrays.
   WebSocket replay is also a bounded public query surface: replay count and
   subscription filter cardinality are explicit budgets, and token-filter replay
   must not multiply the full replay limit by every requested symbol or address.
   Replay payload hydration uses page-level batch reads for projected
   entities, alerts, token intents, and event-token resolutions instead of
   per-event read-model lookups.
5. **One writer per read model.** Each derived read model has exactly one
   runtime writer: `token_radar_current_rows`,
   `token_radar_publication_state`, `token_radar_rank_source_events`,
   `token_radar_target_features`, and `token_radar_target_first_seen` are
   written only by `TokenRadarProjectionWorker`; Token Radar online serving
   reads only `token_radar_current_rows` plus
   `token_radar_publication_state`. `token_radar_rank_source_events` is lazy
   evidence/detail, not leaderboard service. `token_radar_target_features` is
   projection-private intermediate state, not an API, CLI, Pulse,
   notification, or repair read path. Its retention is owned by
   `TokenRadarProjectionWorker`, which runs a bounded private-cache maintenance
   lane from formal `settings.workers.token_radar_projection.private_cache_retention_*`
   settings; rank publication still does not prune retention rows in the hot
   path. `token_radar_current_rows` stores scalar
   `rank_score`, `quality_status`, `degraded_reasons_json`, and
   `factor_snapshot_json`; legacy top-level `asset_json`,
   `primary_venue_json`, `target_json`, `attention_json`, `market_json`,
   `price_json`, and `score_json` blocks are not a live contract. Retired
   `token_radar_rank_history`, `token_radar_snapshot_audit`, and
   `token_radar_projection_coverage` do not participate in online service.
   Token Radar serving rows and target-feature rows require formal
   `target_type_key` / `identity_id` identity before payload or generation
   hashing; missing identity is not recovered from `target_id` or `intent_id`.
   Projection-private target-feature rows are subject to the same contract when
   they are converted into current rows: missing `target_type_key` or
   `identity_id`, missing row-id dimensions (`projection_version`, `window`,
   `scope`, `lane`), missing latest event time, or missing/non-mapping factor
   snapshots fail instead of producing empty serving keys, empty row-id
   segments, `attention` defaults, zero source frontiers, or empty factor
   payloads. Target-feature current-row `created_at_ms` comes from formal
   `last_scored_at_ms`; it is not repaired from `updated_at_ms` or the runtime
   wall clock. The target-feature cache writer itself also requires formal
   projection payload fields before `token_radar_target_features` SQL:
   `lane`, `source_max_received_at_ms`, `source_event_ids_json`,
   `created_at_ms`, and `factor_snapshot_json` must be present with their
   expected scalar/list/mapping shapes, and repository payload shaping does not
   substitute `attention`, `computed_at_ms`, empty provenance arrays, or empty
   factor payloads. The factor snapshot's core score/decision contract is also
   strict at this boundary: `composite.rank_score`,
   `composite.recommended_decision`, and `gates.max_decision` are required
   formal fields, and the cache writer does not coerce missing values into
   `0.0` or `discard`.
   Pulse, Narrative Admission, and Token Profile Current downstream dirty
   targets derive `source_watermark_ms` only from current-row positive
   `source_max_received_at_ms`; missing or invalid source watermarks fail
   closed instead of falling back to `computed_at_ms` or projection runtime
   time.
   Token Radar current-row delete/upsert, target-feature write/delete, and
   target-feature retention write accounting requires real PostgreSQL
   `cursor.rowcount` evidence. Missing, boolean, negative, or otherwise invalid
   rowcount is malformed driver/wiring state, not a default zero- or one-row
   publication count.
   Watched-account `account_token_alerts` are fact-like ingest outputs and use
   the same single-row write evidence boundary: `INSERT ... DO NOTHING`
   created-vs-existing classification requires PostgreSQL `cursor.rowcount`
   equal to `0` or `1`; missing, boolean, negative, multi-row, or otherwise
   invalid rowcount is malformed driver/wiring state.
   Evidence ingest fact writes use that same PostgreSQL evidence boundary:
   `raw_frames`, `events`, and `event_entities` `INSERT ... DO NOTHING`
   classification/counting requires single-row `cursor.rowcount` evidence
   equal to `0` or `1`; missing, boolean, negative, multi-row, or otherwise
   invalid rowcount is malformed driver/wiring state before raw-frame,
   event-created, or inserted-entity results are returned.
   Ranked current-row patching also requires formal ranked-row metadata
   (`normalization_status`, `cohort_status`, `cohort_size`,
   `cohort_in_cohort`, `cohort_metadata`, complete per-family `factor_ranks`,
   `alpha_rank`, `rank`, `rank_score`, `recommended_decision`, and
   `latest_event_received_at_ms`) before mutating the current row or
   `factor_snapshot_json`; missing ranked metadata is not repaired to
   `no_signal`, `not_ranked`, false cohort membership, empty/incomplete rank
   maps, rank `0`, alpha rank `None`, or source watermark `0`. Family rank
   values must be `None` or bounded `0..1` ranks.
   Diagnostic score evaluation consumes the same formal v3 factor snapshot
   contract; missing `composite.rank_score` fails before bucket or IC summaries
   and is not counted as a `0-19` bucket sample. Family rank IC and coverage
   read formal `families.*.score`, not optional `composite.family_scores`
   aliases. Score evaluation also requires
   settlement subject identity from `factor_snapshot_json.subject`
   (`target_type` plus `target_id`) and does not repair missing subject identity
   from current-row top-level `target_type` / `target_id`; this evaluator-only
   rule does not make unresolved attention snapshots invalid globally. CEX
   settlement targets require subject-owned `provider` and `native_market_id`;
   `market.decision_latest` and `instrument` aliases are not settlement identity
   fallbacks. Settlement subject `target_type` is the formal product identity
   type (`Asset` or `CexToken`); direct market-tick target types
   `chain_token` and `cex_symbol` are not settlement subjects and fail before
   market lookup. Asset settlement targets require subject-owned `chain` and
   `address`; `chain_id` and `asset_address` aliases are not settlement
   identity fallbacks. Settlement time comes from `factor_snapshot_json.provenance.computed_at_ms`,
   not from current-row top-level `computed_at_ms` or an epoch-zero fallback.
   Rank-set pre-publication selection also treats rank-input
   `latest_event_received_at_ms` and `lane` as formal fields: missing latest
   event time is not a zero timestamp used to drop the row as expired, and
   missing/unknown lane is not silently excluded from resolved/attention
   selection. Compact rank inputs also require formal `raw_composite_score` and
   `gates_max_decision`, and ranked rows require formal `rank_score` and
   `recommended_decision`; rank selection does not turn missing
   score/gate/decision fields into `0.0` or `discard`. Retired snapshot-row
   sort helpers are not kept as compatibility code; rank publication uses the
   compact rank-input contract rather than `_rank_key`, `raw_alpha_score`
   fallback, or invalid-snapshot demotion.
   Unresolved attention-row `LookupKey/...` identity comes from formal
   `lookup_keys_json` values on the resolution fact, not from display-symbol
   reconstruction. Token Radar `resolution_json` preserves the selected
   resolution's non-empty status plus list-shaped reason/candidate/lookup
   arrays; malformed resolution fields fail before current-row publication
   instead of becoming `NIL` or empty arrays. High-confidence
   `EXACT` / `UNIQUE_BY_CONTEXT` resolutions must also carry formal
   `Asset` or `CexToken` target identity before they can enter the resolved
   lane; malformed target identity is projection damage, not an attention-row
   downgrade. Resolved `Asset` target payloads also require the joined
   `asset_identity_current` explanation fields `asset_identity_confidence`,
   list-shaped `asset_identity_reason_codes`, and non-negative integer
   `asset_identity_conflict_count`; the projection must not repair missing
   identity-current evidence into empty reason arrays or zero conflicts.
   Downstream rank-change fan-out, rank-input venue selection, and Capture
   Tier rank-set dirty payload hashes consume that formal current identity:
   stale `target_type` / `target_id` aliases must not override
   `target_type_key` / `identity_id`, and alias-only current rows fail before
   dirty hashing or downstream enqueue.
   Ingest and resolution reprocess source-dirty enqueue consume formal
   `TokenIntentResolutionDecision` results; dict/object resolver decision
   compatibility is not part of the projection input contract.
   Token Radar generic target-dirty enqueue and source-dirty enqueue
   repositories also require formal queue identity before payload hashing or
   queue SQL: generic target dirty rows require `target_type_key` /
   `identity_id`, and source dirty rows require
   `source_event_id` / `target_type_key` / `identity_id`. They do not restore
   `target_type`, `target_id`, `intent_id`, or `event_id` aliases and do not
   silently skip malformed queue commands.
   Token Radar target/source dirty queue mutation counts for enqueue,
   completion, retry, market-current, and repair/catch-up paths require real
   PostgreSQL `cursor.rowcount` evidence. Missing, boolean, negative, or otherwise
   invalid rowcount is malformed repository/driver state, not a default no-op
   queue write count.
   Rank-source repair target payloads, latest-market-context input/output
   rows, affected-target output rows, and source-projection target request
   lists follow the same formal target contract: `target_type_key` and
   `identity_id` are required before market-context SQL/result mapping,
   rank-source edge repair, target-feature delete/upsert, or source request
   generation. Those helpers do not recover identity from `target_type` /
   `target_id` aliases and do not hide malformed targets as empty repair work.
   Token Radar rank-source edge population returns changed-row counts from
   explicit SQL aggregate rows, and rank-source prune returns changed-row counts
   from PostgreSQL `cursor.rowcount`; missing or invalid count evidence is
   malformed query/driver state, not a default zero-edge update.
   Token Radar target/source dirty completion CAS identity is equally formal:
   target dirty claims require `target_type_key` / `identity_id`, and source
   dirty claims require `projection_version` / `source_event_id` /
   `target_type_key` / `identity_id`; alias mapping may happen before enqueue,
   never after claim when building done/error keys. Dirty-queue lease and retry
   intervals are formal `settings.workers.token_radar_projection` policy, read
   by `TokenRadarProjectionWorker` and passed explicitly into projection
   processing rather than hidden in service-local constants.
   `token_capture_tier` is written only by
   `TokenCaptureTierWorker`; `pulse_agent_jobs`, `pulse_candidate_edge_state`,
   `pulse_candidate_run_budget`, `pulse_target_run_budget`,
   `pulse_agent_runs`, `pulse_agent_run_steps`,
   `pulse_agent_runtime_versions`, `pulse_agent_eval_cases`,
   `pulse_agent_eval_results`, `pulse_candidates`, and
   `pulse_playbook_snapshots` are written only by `PulseCandidateWorker`.
   Signal Pulse public list/detail reads treat present `pulse_candidates` rows
   as a serving contract: `decision_json` must be mapping-shaped and
   `gate_reasons_json`, `risk_reasons_json`, `evidence_event_ids_json`, and
   `source_event_ids_json` must be list-shaped. Malformed present rows are not
   repaired into empty decision text or empty public arrays.
   Pulse agent run and run-step audit `RETURNING` writes require PostgreSQL
   `cursor.rowcount` evidence matching returned-row presence before run or step
   rows are returned; missing, invalid, or mismatched rowcount is malformed
   repository/driver state, not a valid agent audit row.
   Pulse agent runtime-version, eval-case, and eval-result `RETURNING` writes
   use the same required single-row evidence before eval audit rows are
   returned.
   Pulse candidate upsert and low-information hide `RETURNING` writes require
   PostgreSQL `cursor.rowcount` evidence matching returned-row presence.
   Unchanged candidate upserts and no-op hide attempts are valid only as
   rowcount=0 with no row, not fallback readback of an existing public row.
   Pulse agent job enqueue retry budget is the formal
   `settings.workers.pulse_candidate.max_attempts` policy passed by the worker
   into `PulseJobsRepository.enqueue_job(...)`; the repository owns SQL, not a
   fallback retry-budget default.
   Pulse agent job enqueue, claim, success, retry, failure, timeout-cancel, and
   release `RETURNING` mutations validate PostgreSQL rowcount against
   returned-row presence before job state, retry/dead classification, or terminal
   ledger effects are reported. Required enqueue is rowcount=1 with a row;
   optional state transitions accept only rowcount=0/no row or rowcount=1/row.
   Pulse trigger dirty claims validate claimed `window` and `scope` against
   formal worker settings before exact Token Radar or timeline reads; malformed
   dimensions fail through dirty-trigger retry instead of widening to all-public
   evidence.
   Pulse trigger dirty-target done/error/reschedule accounting requires
   PostgreSQL `cursor.rowcount` evidence. Missing, boolean, negative, or
   otherwise invalid rowcount is malformed repository/driver state, not a
   default zero-row dirty-trigger mutation.
   Pulse admission edge-state and candidate edge-budget `RETURNING` writes also
   require PostgreSQL `cursor.rowcount` evidence matching returned-row presence
   before edge rows, optional state rows, or budget booleans are reported.
   Missing, invalid, or mismatched rowcount is malformed repository/driver
   state, not returned-row success.
   Pulse playbook snapshot/outcome `RETURNING` writes must use the same execution
   evidence: snapshot no-change writes are valid only as rowcount=0 with no row,
   changed snapshot and outcome writes require rowcount=1 with a row, and the
   repository must not recover success through a fallback `SELECT`.
   Pulse stale exhausted running-job terminalization width is the formal
   `settings.workers.pulse_candidate.stale_running_terminalization_batch_size`
   worker policy passed into `PulseJobsRepository`; the repository must not own
   a hidden `limit` default.
   `narrative_admissions` is written only by `NarrativeAdmissionWorker`.
   Narrative admission dirty claims validate claimed `window` and `scope`
   against formal worker settings before admission-target or source-set reads;
   malformed dimensions fail through dirty-target retry instead of widening
   scope or restoring a 24h source window.
   Narrative admission dirty-target done/error/reschedule accounting requires
   PostgreSQL `cursor.rowcount` evidence. Missing, boolean, negative, or
   otherwise invalid rowcount is malformed repository/driver state, not a
   default zero-row narrative dirty-target mutation.
   Former narrative LLM read models such as `token_mention_semantics` and
   `token_discussion_digests` have no current runtime writer. Public surfaces
   may read historical rows as legacy context, but current runtime work does
   not refresh them. Public Narrative hydration requires formal
   `target_type` / `target_id` row identity and does not restore old Token Radar
   `type` / `id` aliases before legacy digest lookup. New
   read models must declare their single writer in the owning module's
   ARCHITECTURE.md. `token_profile_current` is written only by
   `TokenProfileCurrentWorker`; it may expose token logos only from ready
   local `token_image_assets` rows. Public `TokenProfileReadModel` treats a
   present `token_profile_current` row as a formal current-row contract:
   `status`, `source_kind`, `quality_flags_json`, and `source_payload_json`
   must be present and well shaped. The projection service emits those JSON
   fields by their storage names, and repository upsert input must not accept
   old `quality_flags` / `source_payload` aliases or empty JSON defaults.
   `token_profile_current_dirty_targets` enqueue is a formal control-plane
   input to that writer: producers must pass positive source watermarks, and
   the dirty repository plus ops image repair must not synthesize them from
   `computed_at_ms`, `updated_at_ms`, tuple identity, or runtime `now_ms`.
   Missing current rows may become explicit pending/unsupported public blocks,
   but malformed present rows are projection damage, not pending state.
   `news_items.content_class`, `news_items.content_tags_json`,
   `news_items.content_classification_json`, `agent_admission_*`,
   `story_identity_json`, and `agent_requirement_*` are written by
   `NewsItemProcessWorker` as item-level material facts; its worker sessions,
   claim budget, lease, retry budget, and processed-item wake emission read the
   formal `settings.workers.news_item_process` contract directly;
   `news_item_agent_runs` and `news_item_agent_briefs` are written only by
   `NewsItemBriefWorker`, whose claim/session/retry/backpressure budgets and
   brief-updated wake emission read the formal
   `settings.workers.news_item_brief` contract directly. `news_item_agent_runs`
   inserts and `news_item_agent_briefs` current upserts require rowcount=1 with
   a returned row before agent audit rows, current brief state, page dirty
   fan-out, or high-signal publication state can advance. Schema-version cleanup
   of current `news_item_agent_briefs` rows through
   `DELETE ... RETURNING news_item_id` requires cursor rowcount to match returned
   ids before stale-brief cleanup accounting is reported. Restoring current
   brief state from an existing completed/failed run requires the persisted
   `news_item_agent_runs.run_id`; missing run identity is a malformed ledger
   row, not permission to call the model again or write an empty
   `agent_run_id`. Completed-run validation, provider failure audit, and
   market-wide agent admission consume formal domain/execution models directly;
   dict/object reflection is not a News item-brief runtime compatibility layer.
   Item-brief entity support consumes the formal
   `NewsItemBriefInputPacket.entity_lanes` / `NewsItemBriefEntityLane`
   contract directly when deriving source-backed market domains; missing
   fields are malformed packet state, not defaults to recover with
   `getattr(..., fallback)`.
   `news_page_rows` is written only by `NewsPageProjectionWorker`; page-row
   JSONB sections such as `token_lanes`, `fact_lanes`, `story`, `source`,
   `signal`, `agent_brief`, `market_scope`, and `agent_admission` are formal
   writer output before payload hashing or SQL, not repository defaults to
   synthesize as empty arrays, empty objects, or pending agent state. News item
   detail reads preserve the same contract once a current page row exists:
   `news_items` may hydrate the base item and evidence detail, but it must not
   repair malformed projected story, market, admission, signal, content, or lane
   fields. News page list reads and high-signal notification candidate reads
   preserve the same projected-row contract; malformed page-row sections fail
   before public payload or notification shaping instead of becoming pending
   agent brief state or unvalidated JSON.
   `news_page_rows` `INSERT ... ON CONFLICT ... RETURNING (xmax = 0)` writes
   classify inserted, updated, and unchanged rows only after PostgreSQL
   `cursor.rowcount` is present, valid 0/1, and matches returned-row presence;
   rowcount=0/no row is the only unchanged projection result, and rowcount=1
   with a returned row is the only changed serving-row result.
   News projection dirty-target enqueue, done/error, and terminal delete counts
   require PostgreSQL `cursor.rowcount` evidence; missing or invalid rowcount is
   malformed repository/driver state, not default zero changed queue work.
   News projection dirty-target claim rows from `UPDATE
   news_projection_dirty_targets ... RETURNING news_projection_dirty_targets.*`
   require cursor rowcount to match returned rows before projection workers treat
   targets as leased work.
   Terminal delete rowcount must match returned deleted rows before terminal
   ledger writes.
   Explicit ops projection dirty repair is a bounded keyset enqueue path, not a
   wide News projection input rebuild: page/brief repair reads only
   `news_item_id`, source watermark, and persisted agent-admission status, and
   source-quality-only repair does not scan `news_items`.
   News configured-source reconciliation follows the same PostgreSQL evidence
   contract: `INSERT INTO news_sources ... ON CONFLICT ... RETURNING *` must
   prove rowcount=1 with a returned source row before inserted/updated source
   rows are reported, and `UPDATE news_sources ... RETURNING *` rowcount must
   match returned disabled source rows before source reconcile rows or disable
   counts are reported. News fetch source claims use the same rule:
   `UPDATE news_sources ... RETURNING sources.*` must prove that cursor rowcount
   matches returned claim rows before `NewsFetchWorker` can treat a source as
   leased for provider work. News fetch-run start requires rowcount=1 for both
   the `news_fetch_runs` running-ledger insert and the matching
   `news_sources.last_fetch_at_ms` update before a run id is returned. News
   fetch-run finalization also uses required single-row
   `UPDATE news_fetch_runs ... RETURNING *` evidence: rowcount=1 with a returned
   run row is the only valid finalized run, and malformed evidence fails before
   `news_sources` status is updated or a fetch-run row is returned.
   News provider observation upserts follow the same required-row contract:
   `INSERT INTO news_provider_items ... ON CONFLICT ... RETURNING *` must prove
   rowcount=1 with a returned provider-item row before inserted/updated
   provider observations are reported; malformed rowcount/row evidence fails
   before fetch-run accounting can treat the provider item as persisted.
   Canonical News item upserts also require rowcount=1 with a returned
   `news_items` row before observation edges, remap cleanup, or fetch dirty-set
   accounting can use the canonical `news_item_id`.
   Observation edge upserts require rowcount=1 before provider-article remap,
   material duplicate remap, summary refresh, or affected-item accounting can
   treat the provider observation as linked to the canonical item.
   Provider-article and material duplicate edge-remap CTEs must validate cursor
   rowcount against returned old item-id rows before old-item summary cleanup,
   dirty-target remap, or affected-item accounting uses those ids.
   Observation summary `UPDATE news_items ... RETURNING items.*` refreshes must
   prove rowcount=1 with the returned current item row before affected-item
   accounting uses refreshed source/provider-article aggregates; old zero-edge
   cleanup paths may observe rowcount=0/no row only as explicit optional cleanup
   state, never by fallback `SELECT` readback.
   Old-item representative reselection uses `UPDATE news_items ... RETURNING
   items.*` with optional single-row rowcount evidence: rowcount=0/no row is
   only an explicit no-representative-edge cleanup result, and rowcount=1/row is
   the only valid representative fact refresh before item-scoped derived facts
   are cleared or affected-item accounting continues.
   `NewsItemProcessWorker` claim rows use the same execution evidence:
   `claim_unprocessed_items` updates `news_items` to `processing` through
   `UPDATE news_items ... RETURNING items.*` and must validate cursor rowcount
   against returned claim rows before deterministic item processing treats those
   items as leased.
   Canonical edge-remap cleanup follows the same contract: zero-edge old
   `news_items` deletes must validate `DELETE ...
   RETURNING` cursor rowcount against returned rows before cleanup booleans are
   reported.
   `news_source_quality_rows` is written only by
   `NewsSourceQualityProjectionWorker`. The source-quality writer reads
   statement timeout, claim batch, lease, retry, and windows from formal
   `news_source_quality_projection` worker settings. `cex_oi_radar_rows`,
   `cex_oi_radar_publication_state`, and `cex_detail_snapshots` are written
   only by `CexOiRadarBoardWorker`; detail snapshot serving identity requires
   formal `snapshot_id` / `target_type` / `target_id` / `exchange` /
   `native_market_id` plus non-empty `base_symbol` / `quote_symbol` before
   builder output, payload hashing, or upsert. Detail snapshot status fields
   `status`, `baseline_status`, and `coinglass_status` are also formal
   writer-output enums before payload hashing or upsert. The detail builder
   also requires the worker-selected non-empty `period` before mapping OI delta
   slots, so missing runtime period cannot be encoded as an `unknown` degraded
   reason. It must not use builder placeholders such as `cex_token:unknown`,
   builder-local `binance` exchange recovery, or repository defaults that
   restore missing identity, market symbols, or states to `CexToken`,
   `binance`, empty string, `USDT`, `partial`, `missing`, or `unavailable`.
   Detail snapshot payload hashes also reject legacy DB column aliases such as
   `level_bands_json`, `degraded_reasons_json`, and `source_refs_json`; those
   names are read-row mapping details, not writer input contracts. The detail
   builder follows the same rule for level bands and rejects `level_bands_json`
   rather than treating a DB column alias as a board/enrichment DTO field. When
   formal `level_bands` are present, each band must carry `kind` and numeric
   `price` before source refs or snapshot payload are built; the builder must
   not default missing kind to `level` or skip bands with missing price. The
   detail builder and CoinGlass enrichment stage also require present
   `degraded_reasons` to be list-shaped with non-empty string items, so scalar
   strings or malformed items cannot be laundered into snapshot payload
   reasons. It also
   requires the board/enrichment row's formal `observed_at_ms` and
   `observed_at_source=provider|computed` tuple instead of inferring source from
   timestamp equality. The detail repository payload hash follows that same
   tuple contract whenever `observed_at_ms` is present, and does not infer
   provider freshness from `computed_at_ms`. Detail repository JSON list
   payloads (`level_bands`, `degraded_reasons`, and `source_refs`) must be
   present and list-shaped before payload hash or SQL; missing fields are not
   restored to empty arrays.
   The Binance worker passes
   `exchange="binance"` into detail snapshot construction explicitly. Token
   Case/Search Inspect missing-detail blocks may expose degraded product
   state, but only persisted `cex_detail_snapshots` rows own `snapshot_id` and
   `exchange`; read paths must not synthesize those projection identity fields.
   CEX detail repository read methods require non-empty target or market query
   identity before SQL, instead of treating empty strings as a cache miss. The
   public `/api/cex/detail` route also validates target and market query modes
   before repository reads, so partial target keys, blank market exchange
   values, or requests carrying both lookup modes become explicit bad requests
   rather than `data:null`, target-first precedence, or server errors.
   Binance OI radar row construction also requires selected universe route
   `native_market_id` and `base_symbol` before provider IO or board-row
   construction, so malformed route identity cannot become a skipped symbol,
   empty-base board row, or successful empty board. Runtime Binance OI provider
   wiring maps formal integration DTO fields into `CexOiTicker24h`,
   `CexFundingPremium`, and `CexOpenInterestPoint` and fails malformed
   integration rows before returning domain provider DTOs. The board builder
   consumes those DTO fields directly; malformed provider objects returned by
   those sequences fail before scoring instead of being restored to `None`
   metrics through object-reflection defaults. CEX board payload hashes
   require non-empty `period`, `target_id`, `native_market_id`,
   `base_symbol`, and `quote_symbol` before board key construction, row-id
   hashing, payload hashing, or upsert, and include provider-observed market
   freshness only. Each board row must carry a formal `observed_at_ms` plus
   `observed_at_source=provider|computed` tuple before payload hashing or SQL;
   missing source cannot be treated as provider freshness, and missing
   timestamp cannot be replaced with `computed_at`. Computed fallback
   `observed_at_ms` values and successful empty-board attempt times are
   projection metadata, not content signatures that may rewrite serving rows.
   Board scoring explanation is also formal writer output:
   `score_components` must be present and mapping-shaped before payload hash or
   SQL, not restored to `{}` by the repository. Board delete/upsert write
   accounting also requires real PostgreSQL `cursor.rowcount` evidence; missing
   or invalid rowcount is malformed driver/wiring state, not a default zero- or
   one-row write. The public `/api/cex/radar-board` route preserves the same
   contract: repository payloads must include a formal `rows` list and
   mapping-shaped `score_components_json` per row instead of route-local `[]` or
   `{}` defaults.
   CoinGlass enrichment also
   requires row `base_symbol` before provider IO; missing base is malformed
   writer output, not provider-unavailable degraded state. The enrichment
   stage emits formal `coinglass_status` on every row it returns, including
   `unavailable` for disabled or out-of-budget enrichment, and the detail
   builder validates that status instead of defaulting it;
   CEX derivative-series history upserts also skip unchanged overlapping
   provider-history conflict rows with `IS DISTINCT FROM` and required
   `cursor.rowcount` evidence instead of unconditional `DO UPDATE`; missing or
   invalid rowcount is malformed driver/wiring state, not a default one-row
   write. Their series identity requires
   non-empty provider, exchange, native market id, metric, and period before
   hash construction or SQL, because PostgreSQL `NOT NULL` does not reject
   empty text business keys; each history point also requires a mapping-shaped
   `raw_payload` before JSONB SQL so missing provider evidence cannot collapse
   into an empty object. Detail snapshot upsert write accounting also requires
   real `cursor.rowcount` evidence; missing or invalid rowcount is malformed
   driver/wiring state, not a default no-op write.
   `macro_sync_windows` is Macro's sync control plane, not product truth.
   Enqueue and claim `RETURNING` writes validate PostgreSQL rowcount against
   returned-row presence before reporting enqueued, no-work, or claimed
   window state; returned-row presence alone cannot start provider work or
   classify sync-window state.
   `macro_observation_series_rows` and `macro_view_snapshots` are written only
   by `MacroViewProjectionWorker`. That worker reads statement timeout,
   claim batch, lease, retry, lookback, and per-series bounds from the formal
   `macro_view_projection` worker settings; the worker must not keep runtime
   fallback constants for those execution budgets. `macro_view_snapshots`
   JSON sections are also part of the writer contract: missing
   `panels_json`, `indicators_json`, `triggers_json`, `data_gaps_json`,
   `source_coverage_json`, `features_json`, `chain_json`, `scenario_json`, or
   `scorecard_json` must fail before payload hash/upsert instead of being
   restored to `{}` or `[]` by the repository.
   Single writer is necessary but not sufficient for runtime safety. A current
   read model must also have a bounded physical lifecycle: row count must be
   proportional to product cardinality and active windows, not to worker run
   count, wake count, retry count, or wall-clock uptime. Serving primary keys
   for current read models must not include `generation_id`, `run_id`,
   `attempt_id`, timestamp-derived ids, or UUIDs. Those identities are allowed
   only in audit/control ledgers with explicit retention or in short
   transaction staging that is not a public serving contract. Active pointers
   hide old generations from readers; they do not make the storage, indexes,
   planner statistics, autovacuum work, or replication/WAL pressure bounded.
   Current-row projections must expose an observable unchanged path: when the
   source signature or dirty-target content did not change, the worker updates
   publication state at most and writes zero serving rows. Use `payload_hash`
   or `IS DISTINCT FROM` gates; do not delete/reinsert unchanged current rows.
   Current-row `RETURNING true AS changed` writes, including
   `macro_view_snapshots`, `macro_daily_briefs`, `asset_identity_current`,
   `token_capture_tier`, `market_tick_current`, and `token_profile_current`,
   require PostgreSQL rowcount evidence matching returned-row presence before
   changed booleans, downstream dirty enqueue decisions, wake decisions, or
   worker write counts are reported.
6. **Wake is not truth.** PostgreSQL `NOTIFY` channels
   (`market_tick_written`, `market_tick_current_updated`,
   `resolution_updated`, `token_radar_updated`) carry hint payloads only;
   consumers re-read DB on wake. Market tick writers wake
   `MarketTickCurrentProjectionWorker`, which emits
   `market_tick_current_updated` after `market_tick_current` changes; Token
   Radar listens to that current-ready channel. Every listener must have a
   bounded `interval_seconds` loop that re-reads durable queues or bounded
   read models so a missed `NOTIFY` cannot stall the pipeline. Runtime workers
   must not compensate for missed wakes by scanning large fact windows; missed
   enqueue recovery belongs to explicit bounded ops repair commands that
   enqueue control rows only.
7. **No runtime compatibility layer.** Hard cuts delete the old runtime
   path. No `_overlay_*`, no `fallback_to_v2_snapshot`, no "if missing fall
   back to the old field". Migration code and rollback docs may reference
   removed names; runtime, public API, and frontend code may not.
8. **Capture lanes own market persistence.** `MarketTickStreamWorker` writes
   Tier 1 WebSocket ticks, `MarketTickPollWorker` writes Tier 2 REST ticks,
   and ingest inline capture writes Tier 3 ticks. `LivePriceGateway` is
   cache/publish only; it never writes market facts, and its fan-out target
   limit / tick TTL come from `settings.workers.live_price_gateway`.
9. **Observable IO state.** Each WS provider exposes a connection state
   (`disconnected | connecting | authenticating | subscribed | streaming |
   failed`) with a `last_state_change_at_ms`. The snapshot gate exposes
   outcome counters (`immediate_complete | debounced_complete |
   debounced_timeout | non_tw_channel`). Both surface through
   `/api/status`.
10. **Audit ledger truth.** Every Signal Pulse decision must be replayable
   from `pulse_agent_runs` and `pulse_agent_run_steps`. Insufficient data
   finishes as an abstain decision with the audit row written; no path may
   return a decision without an audit row, and no path may invent a
   confidence or display status to avoid abstaining.
11. **Public query boundaries fail closed.** API route defaults own product
   defaults such as `scope=all` or `scope=matched`; shared validators only
   validate. Malformed scope/window values return structured bad requests and
   must not be coerced into another valid read scope before PostgreSQL queries.
12. **Agent execution is an operational plane, not product truth.**
   `AgentExecutionGateway` owns project execution mechanics around LiteLLM:
   structured JSON object dispatch, application-side Pydantic validation,
   trace metadata, usage, lane bulkheads, rate limits, timeouts, circuit
   breakers, reservation, and request/result audit envelopes. Model capability
   adaptation belongs here: domains submit stage specs with Pydantic output
   types and never branch on provider, model, or response format. Domain
   workers still own admission, claim, retry, finalize, read-model writes,
   and business validation. There is no central durable `agent_tasks`
   queue; PostgreSQL domain facts and read models remain the truth. Pulse
   multi-stage runs reserve the single `pulse.decision` lane before job claim.
   Every LLM-backed worker that can burn business attempts reserves lane capacity,
   circuit, and RPM before durable queue claim; batch workers request explicit
   `rate_units` for the maximum provider calls they want to execute and claim
   only the actual `reservation.rate_units` returned by the gateway. Pulse
   internal audit stages reuse the same `pulse.decision` reservation.
   No-start backpressure does not claim work, write business run ledgers, or
   burn provider attempts. Provider-started validation/publication failures
   write the domain run ledger with `execution_started=true`. Lane `priority`
   is an operator-facing policy label rather than a strict scheduler.

Cross-cutting primitives that implement these invariants:

- `MarketTick` — value type in
  `domains/asset_market/types/market_tick.py`; the append-only provider
  tick fact contract across domains.
- `enriched_events` — event projection rows written with `events` so
  social-signal context can be replayed without provider calls.
- `token_capture_tier` — rebuildable capture-control projection with
  `TokenCaptureTierWorker` as its only runtime writer.
- `token_image_assets` — rebuildable local media mirror state written only by
  `TokenImageMirrorWorker`. Provider logo URLs are source inputs for the
  mirror and are never public image URLs.
- `runtime.bootstrap()` — composition entry point that builds
  `DBPoolBundle`, provider wiring, repositories, the canonical worker
  map, `WorkerScheduler`, API/WebSocket surfaces, readiness dependencies,
  and lifecycle ownership.
- `DBPoolBundle` — owns `api_pool`, `worker_pool`, `lock_pool`, and
  `wake_pool`. HTTP/WebSocket reads use the API pool, background worker
  SQL uses the worker pool, long-lived single-writer advisory locks use
  the lock pool, and wake emit/listen traffic uses the wake pool so read
  and worker traffic cannot be starved by projection locks or listeners.
- `worker_manifest.py` and `WorkerScheduler` — declare the canonical
  worker keys/classes/lane contracts and own worker start/stop/status semantics.
- `LLMGateway` and `AgentExecutionGateway` — `LLMGateway` owns low-level
  OpenAI transport/client/trace-export lifecycle; `AgentExecutionGateway`
  is the single agent execution path used by Social, Watchlist,
  Narrative, Pulse, and future LLM lanes. It resolves the lane capability
  profile and chooses the structured-output strategy before any provider
  call.
- Model-execution provider wiring reads known lane settings from
  `workers.agent_runtime.lanes` directly. The Pulse decision provider's
  pipeline timeout comes from `pulse.decision.timeout_seconds`; a missing lane
  is malformed runtime configuration, not a provider-local fallback.
- Wake emission/listening is composed via
  `DBPoolBundle.wake_emitter()` and `DBPoolBundle.wake_listener()`.
  Domain workers receive wake dependencies by injection and never call
  `pg_notify` directly.
- `WiredProviders` domain bundle fields are composition-root contracts. Worker
  factories read bundle roots directly, such as `ctx.providers.news_intel` and
  `ctx.providers.cex_market_intel`; missing domain bundles are malformed
  runtime wiring. Optionality belongs to concrete provider handles inside an
  existing bundle, where an enabled worker can surface a redacted
  `unavailable` reason.
- Runtime status and diagnostics surfaces follow the same root contract:
  `/readyz` and ops diagnostics read `runtime.providers.asset_market`
  directly. A missing domain bundle is malformed runtime wiring; only concrete
  provider handles inside the bundle may be `None` and reported as disabled or
  disconnected IO state.
- Asset Market provider health is part of that formal bundle contract. Ops
  diagnostics reads `runtime.providers.asset_market.provider_health` directly;
  missing provider health support is malformed provider-bundle wiring, not an
  empty inventory.
- Asset Market worker factories follow the same bundle-field contract. They
  read `cex_market`, `dex_quote_market`, `dex_profile_sources`,
  `dex_discovery_market`, and `stream_dex_market` directly from
  `AssetMarketProviders`; a missing field is malformed bundle wiring, while a
  present field value of `None` can surface an enabled worker as unavailable.
- Asset Market startup failure cleanup follows the same rule for the upstream
  `OkxProviderBundle`: if the bundle object exists, cleanup reads
  `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` as formal
  fields. Missing fields are recorded as cleanup failures on the original
  startup error, not ignored as absent providers.
- Configured Asset Market provider handles are concrete protocol contracts, not
  optional capability bags. When GMGN OpenAPI is configured, the DEX provider
  must expose `token_quotes(...)` and `token_profile(...)` directly; missing
  methods are malformed wiring, not a reason to fall back to OKX quotes or omit
  the GMGN profile source.
- CEX Market Intel and News Intel worker factories also read their formal
  provider-bundle fields directly (`oi_market`, `coinglass_derivatives`,
  `feed_client`, and `brief_provider`). Missing fields are malformed
  provider-bundle wiring; `None` field values are the only supported
  unavailable-provider state inside an existing bundle.
- CEX Market Intel provider wiring uses the same formal worker settings
  contract when gating optional enrichment. CoinGlass construction reads
  `settings.workers.cex_oi_radar_board.enabled` and
  `.coinglass_enrichment_limit` directly, and the board worker passes formal
  period/build-limit and `.coinglass_level_limit` into downstream builder and
  enrichment services explicitly; missing fields are malformed runtime
  configuration, not "disabled", "no enrichment", default-period, default-limit,
  or default-level fallbacks.
- Worker factory sentinels read `settings.workers.<name>` directly. Missing
  worker settings blocks are malformed runtime configuration; sentinel workers
  must not default absent configs to enabled or synthesize placeholder settings.
  When a sentinel must flip `enabled` for disabled or intentionally-not-started
  status, it clones the formal Pydantic worker settings with
  `model_copy(update={"enabled": ...})`; it must not dump arbitrary objects,
  inspect `__dict__`, or build `SimpleNamespace` compatibility settings.
- `WorkerBase` reads core worker settings directly from the formal settings
  object: `enabled`, `interval_seconds`, and `backoff.base_ms/max_ms`. Defaults
  belong to `PerWorkerSettings` / `workers.yaml` merge, not to runtime fallback
  constants inside the base class.
- CLI ops one-shot worker commands follow the same settings boundary. They read
  the relevant `settings.workers.<name>` block directly for worker-specific
  timeouts and advisory lock keys instead of synthesizing CLI-local defaults.
  When they construct a worker, they use its formal `_advisory_lock_key()`
  method rather than accepting a bare `SINGLE_WRITER_KEY` attribute as a second
  lock-key contract. One-shot overrides such as `batch_size` are applied by
  cloning the formal Pydantic settings object with `model_copy(update=...)`;
  ops must not dump arbitrary objects or synthesize `SimpleNamespace` settings.
- `DBPoolBundle` sizes the wake pool from manifest-declared wake listeners and
  the formal `settings.workers` tree. Missing `settings.workers` or a missing
  wake worker settings block is malformed runtime configuration, not zero wake
  listener demand.
- Runtime News provider-contract status reads
  `runtime.settings.news_intel.sources` directly. Missing News Intel settings
  shape is malformed runtime configuration, not an empty configured-source
  set.
- Ops diagnostics config and watchlist sections read the formal runtime
  settings contract directly. Missing `runtime.settings` or required settings
  fields are malformed runtime configuration, not empty config, disabled
  provider flags, or idle watchlist state.
- Ops diagnostics queue summaries read the formal API pool connection contract
  directly through `runtime.db.api_pool.connection()`. Missing DB/API pool
  wiring is malformed runtime wiring, not an empty queue list.
- Worker queue-health enrichment follows the same DB read contract. It
  constructs `runtime.db.api_pool.connection()` before fallback handling;
  missing connection support is malformed runtime wiring, while real
  context-enter/query failures remain queue-health unavailable state.
- Runtime readiness does not keep unused notification-summary helpers that
  swallow repository errors as empty payloads. Notification public reads and
  worker status must use their owning route/worker contracts directly.
- Collector diagnostics are a formal status contract. Ops diagnostics read
  `runtime.collector.status.to_dict()` and `runtime.collector.upstream_client`
  directly; missing collector status support is malformed runtime wiring, not
  an empty details payload.
- Collector snapshot-gate timing is a formal worker settings contract.
  `CollectorService` reads `settings.snapshot_timeout_seconds` directly from
  `settings.workers.collector`; missing timeout support is malformed worker
  settings, not a 0.5-second service-local default.
- `MarketTickStreamWorker` is constructed only through the formal runtime
  worker contract: `settings.workers.market_tick_stream`, the DB pool bundle,
  the configured stream provider, and the wake emitter. It reads
  `subscription_limit` and `stream_cycle_seconds` directly from settings and
  must not synthesize settings, accept `db` / `wake_bus` aliases, or override
  stream cadence or subscription limits through constructor compatibility
  parameters.
- `MarketTickPollWorker` is constructed only through the formal runtime worker
  contract: `settings.workers.market_tick_poll`, the Asset Market provider
  bundle, the DB pool bundle, and the wake emitter. It must not synthesize
  settings, accept individual `dex_quote_market` / `cex_market` provider
  handles, or override `batch_size` / `interval_seconds` through constructor
  compatibility parameters.
- `MarketTickCurrentProjectionWorker` follows the formal market-current
  projection settings contract. It reads `statement_timeout_seconds`,
  `batch_size`, `lease_ms`, and `retry_ms` directly from
  `settings.workers.market_tick_current_projection`; retry and lease behavior
  must not be supplied by runtime default constants or settings
  `getattr(..., default)` fallbacks.
- `TokenCaptureTierWorker` follows the same formal worker settings contract.
  It receives `settings.workers.token_capture_tier` and the DB pool bundle from
  the worker factory, reads `batch_size`, `ws_limit`, `poll_limit`, and
  `lease_ms` directly, and must not synthesize settings or accept constructor
  overrides for batch/window limits or interval cadence.
- `EventAnchorBackfillWorker` follows the formal event-anchor catch-up
  contract. It receives `settings.workers.event_anchor_backfill`, the DB pool
  bundle, the Asset Market provider bundle or an explicitly injected capture
  service, and the wake emitter from the worker factory. It reads
  `batch_size`, `concurrency`, `max_attempts`, `lease_ms`, `min_age_ms`,
  `active_window_ms`, `max_anchor_lag_ms`, and
  `statement_timeout_seconds` directly from settings; it must not synthesize
  settings, accept `db` / `wake_bus` aliases, accept individual
  `dex_quote_market` / `cex_market` handles, or override limits through
  constructor compatibility parameters.
- `TokenProfileCurrentWorker` follows the formal profile-current projection
  settings contract. It reads `statement_timeout_seconds`, `batch_size`,
  `lease_ms`, and `retry_ms` directly from
  `settings.workers.token_profile_current`; `retry_ms` belongs to the formal
  workers schema, not to a runtime `DEFAULT_RETRY_MS` fallback or helper
  default. `rebuild_token_profile_current_once(...)` requires explicit limit,
  lease, and retry arguments from its caller.
- `TokenImageMirrorWorker` follows the formal image-mirror settings contract.
  It reads `statement_timeout_seconds`, `batch_size`, `lease_ms`, and
  `retry_ms` directly from `settings.workers.token_image_mirror`; image retry
  cadence belongs to the workers schema, not to a runtime
  `DEFAULT_RETRY_MS` fallback or service-local retry default.
- `AssetProfileRefreshWorker` follows the formal profile-source refresh
  settings contract. It reads `statement_timeout_seconds`, `batch_size`,
  `lease_ms`, `provider_retry_ms`, `ready_refresh_ms`,
  `missing_refresh_ms`, and `error_refresh_ms` directly from
  `settings.workers.asset_profile_refresh`; provider-block retry cadence and
  ready/missing/error source-cache refresh cadences belong to the workers
  schema, not to runtime defaults, repository constants, or service-local
  policy fallbacks.
- `ResolutionRefreshWorker` follows the formal discovery refresh settings and
  wake contract. It receives `settings.workers.resolution_refresh`, the DB
  pool bundle, the configured discovery provider, and the wake emitter from the
  worker factory. It reads `chain_ids`, `max_attempts`, `batch_size`,
  `lease_ms`, `hot_not_found_retry_ms`, and `reprocess_limit` directly from
  settings and passes lookup running/claim timing explicitly into the
  discovery repository; it must not accept constructor chain overrides, unused
  quote providers, `wake_bus` aliases, repository-local lookup timing
  constants, read-only due-list repository helpers, or settings fallback
  defaults. Discovery claim rows and lookup result running/found/error writes
  require PostgreSQL rowcount evidence: claim rowcount must match returned rows,
  start/fail return rows require rowcount=1 with `RETURNING *`, and finish
  requires rowcount=1 before result state is reported. Affected-intent reprocess consumes formal
  `TokenIntentResolutionDecision` results before enqueuing Token Radar
  source-dirty rows; loose resolver decision objects are malformed state, not
  empty dirty work.

## Package Roots

| Root | Responsibility |
|------|----------------|
| `app/` | Composition root plus HTTP, WebSocket, and CLI surfaces. `app/runtime/bootstrap.py` wires `DBPoolBundle`, providers, repositories, manifest-owned workers, `WorkerScheduler`, readiness, and lifecycle. `app/surfaces/{api,cli}/` translate public inputs and outputs. Wake mechanics flow through `DBPoolBundle.wake_emitter()` / `wake_listener()`. |
| `domains/` | Product domains. Each domain owns its repositories, queries, services / scoring, read models, and runtime workers. |
| `integrations/` | External adapters for GMGN, OKX, LiteLLM, and other provider APIs. They translate third-party API shapes but do not own product decisions. |
| `platform/` | Config, PostgreSQL infrastructure (client, migrations, audit, Alembic), logging, and runtime paths. Platform never imports product domains. |

Top-level entry shims `cli.py` and `__main__.py` exist only because `pyproject.toml` points the installed command at `parallax.cli:main`. They contain no logic.

## Role Markers

Plans and subsystem architecture docs may tag files with these role markers.
They are descriptive labels for ownership and data-flow review; dependency
direction is still enforced by the package rules below.

| Marker | Meaning |
|--------|---------|
| `[ADAPTER]` | Translates third-party shapes such as GMGN, OKX, macrodata-cli, or LiteLLM into internal values. Does not own product decisions. |
| `[COMMAND]` | Handles write-side use cases: ingesting events, resolving identity, refreshing facts, or writing material observations. |
| `[FACT]` | Owns persisted business facts or value types that represent those facts. |
| `[WAKE]` | Emits or consumes wake hints such as LISTEN/NOTIFY. Wake hints are never the source of correctness. |
| `[PROJECTION]` | Builds derived read models from facts. Projection output must be rebuildable. |
| `[READ MODEL]` | Product-facing derived state such as Token Radar rows, profile blocks, or Signal Pulse candidates. |
| `[QUERY]` | Owns read-side queries over facts or read models. |
| `[SCORING]` | Computes deterministic scores, gates, readiness, and diagnostics from query results. |
| `[SURFACE]` | HTTP, WebSocket, or CLI translation layer. Surfaces do not perform provider calls, scoring, token resolution, or raw SQL joins. |
| `[UI]` | Frontend code that consumes public contracts. |
| `[DELETE]` | Legacy runtime path scheduled for removal by an active hard-cut plan. |

## Domains

| Domain | Owns |
|--------|------|
| `domains/ingestion/` | GMGN public-stream frame handling, snapshot gate, handle filtering, raw public-stream normalisation, collector status. |
| `domains/evidence/` | Canonical Twitter event model, event identity, text projection, entity extraction, evidence and entity persistence, ingest orchestration. |
| `domains/asset_market/` | Asset registry, chain/address identity, asset identity evidence/current identity selection, exact-token profile source cache and current profile projection, append-only `market_ticks`, rebuildable `token_capture_tier`, cache/publish-only live price gateway, discovery, and CEX route sync. |
| `domains/token_intel/` | Token evidence, token intents, deterministic resolution, target-first search read model and token-target views with explicit caller-owned query boundaries, Token Radar feature aggregation, current-row publication state, `token_factor_snapshot_v3_social_attention` construction, factor-snapshot projection, evaluation diagnostics, signal alerts. |
| `domains/narrative_intel/` | Current `narrative_admissions` source-set read model, legacy narrative currentness composition, and narrative context consumed by API composition and Pulse evidence packets. Former per-mention semantics and discussion-digest LLM lanes have no current runtime writer. |
| `domains/notifications/` | Notification rules, repository, delivery, workers, candidate types. |
| `domains/pulse_lab/` | Signal Pulse read model, factor-snapshot candidate gate / worker, unified decision runtime policy, stage replay ledger, and pulse persistence. |
| `domains/watchlist_intel/` | Watchlist handle-level topic summaries, signal/all handle timeline read model, summary job queue, and handle summary worker. |
| `domains/news_intel/` | Configured news source ingestion, news item facts, token mention observations, fact candidates, item-scoped agent brief read model, and the News page read model. |
| `domains/cex_market_intel/` | Centralized exchange derivative series and Binance OI radar board projection. |
| `domains/macro_intel/` | `macro_sync` fact ingest from packaged macrodata-cli bundles, macro sync/import audit, deterministic macro feature/regime/scenario scoring, and the Macro read model. |
| `domains/account_quality/` | Account-quality profile/stat/snapshot read models, account-quality read service, account-alert read service, and explicit ops-only maintenance. Account-alert read windows and limits are caller-owned query boundaries, not read-service defaults. |

## Module Architecture Documents

Global architecture stays intentionally small. Important subsystems keep their
own maps next to the code they describe, and this file links to them.

| Module | File | Covers |
|--------|------|--------|
| Token Radar and token identity | [`src/parallax/domains/token_intel/ARCHITECTURE.md`](../src/parallax/domains/token_intel/ARCHITECTURE.md) | GMGN frame to token evidence, intents, deterministic resolution, discovery / reprocess, market ticks, radar projection, and hard identity boundaries. |
| Narrative intelligence | [`src/parallax/domains/narrative_intel/ARCHITECTURE.md`](../src/parallax/domains/narrative_intel/ARCHITECTURE.md) | Current `narrative_admissions` source-set ownership, legacy narrative currentness reads, Pulse/API narrative context, and retired LLM lane hard-cut contracts. |
| Asset market and market tick capture | [`src/parallax/domains/asset_market/ARCHITECTURE.md`](../src/parallax/domains/asset_market/ARCHITECTURE.md) | Asset identity evidence ledger, `MarketTick` schema, capture-tier / stream / poll workers, cache-only live fan-out, profile / discovery workers, provider capability model. |
| CEX market intelligence | [`src/parallax/domains/cex_market_intel/ARCHITECTURE.md`](../src/parallax/domains/cex_market_intel/ARCHITECTURE.md) | Binance USDT perpetual universe consumption, OI radar board read model, CEX detail snapshots, and snapshot-only Token Case / Agent read paths. |
| Signal Pulse pipeline | [`src/parallax/domains/pulse_lab/ARCHITECTURE.md`](../src/parallax/domains/pulse_lab/ARCHITECTURE.md) | Candidate gate, agent route policy, stage runtime, decision persistence, audit ledger, abstain contract. |
| News intelligence | [`src/parallax/domains/news_intel/ARCHITECTURE.md`](../src/parallax/domains/news_intel/ARCHITECTURE.md) | Configured source ingestion, raw news item facts, token mention observations, fact candidates, item briefs, and the News page read model. |
| Macro intelligence | [`src/parallax/domains/macro_intel/ARCHITECTURE.md`](../src/parallax/domains/macro_intel/ARCHITECTURE.md) | `macro_sync` fact ingest, macro observation facts, deterministic `macro_regime_v4` feature/regime/scenario scoring, module v3 views, and Macro projection ownership. |
| Account quality | [`src/parallax/domains/account_quality/ARCHITECTURE.md`](../src/parallax/domains/account_quality/ARCHITECTURE.md) | Account profile/stat/snapshot read-model ownership, ops-only backfill, and public account-quality read services. |

When a subsystem needs more than a short row here, add
`src/parallax/domains/<domain>/ARCHITECTURE.md` and link it from this
table. Keep local docs minimal, current, and tied to code changes.

## Dependency Direction

Within a domain, the allowed sequence is:

```
types/config → repositories/queries → services/scoring → read_models/runtime → app surfaces
```

| Layer | May import from |
|-------|-----------------|
| `domains/<d>/types`, `domains/<d>/config` | stdlib, third-party, same-domain `types`. |
| `domains/<d>/providers.py` | stdlib, third-party typing primitives, and same-domain or interface value types. Pure provider contracts only; no `integrations/*`, `platform/db`, or `platform/paths`. |
| `domains/<d>/repositories`, `domains/<d>/queries` | own domain's `types`, `platform/db`, stdlib, third-party. **Never** imports `services/`, `runtime/`, `read_models/`. Owns SQL. |
| `domains/<d>/services`, `domains/<d>/scoring` | own domain's `types`, `providers.py`, `repositories`, `queries`, plus other domains' `interfaces.py` only. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `domains/<d>/read_models` | own domain's `types`, `repositories`, `queries`, plus other domains' `interfaces.py`. **No raw SQL** — query modules live in `repositories/` or `queries/`. |
| `domains/<d>/runtime` | own domain's `services`, `providers.py`, `repositories`, `queries`, `scoring`, plus other domains' `interfaces.py`. **No `integrations/*`, `platform/db`, or `platform/paths`.** |
| `app/runtime/providers_wiring.py` | Service-process composition module. The only service-runtime file that joins concrete `integrations/*` clients with domain Provider contracts. It may translate supplier shapes such as OKX chain indexes into domain values. |
| `app/runtime/bootstrap.py` | Runtime orchestration: builds `DBPoolBundle`, repositories, workers, surfaces, readiness dependencies, and lifecycle. Imports `wire_providers(...)` / `WiredProviders`; does not import concrete integrations or domain provider modules directly. |
| `app/runtime/worker_manifest.py` and `app/runtime/worker_scheduler.py` | Canonical worker key/class/lane inventory plus start, stop, close, status, and unhealthy-reason semantics. |
| `app/runtime` | composition root: may import any domain runtime, repository, or interface to wire the process, subject to the dedicated Provider wiring rule above. |
| `app/surfaces/api`, `app/surfaces/cli` | domain `interfaces.py` and read services. **No domain SQL, scoring, settlement, token resolution, or notification rules** — surfaces translate public inputs into domain calls. |
| `platform/*` | stdlib, third-party. **Never** imports `domains/`, `integrations/`, or `app/`. |
| `integrations/*` | stdlib, third-party, `platform/*`. They wrap external APIs; they do not import `domains/` or `app/`. |

Cross-domain imports MUST go through the target domain's `interfaces.py` (or `_constants.py` for leaf data). `tests/architecture/test_src_domain_architecture.py::test_cross_domain_imports_use_interfaces` enforces this.

Raw SQL (`conn.execute(...)`) lives ONLY in `repositories/`, `queries/`, `platform/db/`, or `app/runtime/` health checks. `tests/architecture/test_src_domain_architecture.py::test_raw_sql_is_owned_by_repositories_queries_or_app_runtime` enforces this.

Legacy `assets`, `asset_aliases`, `asset_venues`, and `asset_market_snapshots` tables have no runtime writers. `tests/architecture/test_worker_runtime_contracts.py::test_legacy_asset_tables_have_no_runtime_writers` enforces this; `tests/architecture/test_worker_runtime_contracts.py::test_legacy_asset_repository_is_not_imported` bans the deleted `AssetRepository` / `MarketRepository` classes. SocialEvent closed-loop harness tables are deleted; Pulse market reads go through `RegistryRepository.chain_token_market_target(...)` + `MarketTickRepository.latest_at_or_before(...)` rather than `asset_market_snapshots`.

Transaction ownership follows the same rule: domain services and runtime workers use repository/session Unit of Work methods, not `platform.db.postgres_client.transaction` directly. Repositories and `app/runtime/repository_session.py` own the concrete PostgreSQL transaction context.

Repository-owned fact/control upserts that return business rows must prove the
mutation with PostgreSQL cursor rowcount plus `RETURNING` evidence. In
particular, Asset Market registry asset, CEX token, price-feed, and US equity
symbol upserts require rowcount=1 with a returned row; post-write readback is not
a valid Kappa/CQRS execution proof.

PostgreSQL table lifecycle follows the hot/cold contract in
`docs/references/POSTGRES_PERFORMANCE.md`: compact read models are the only hot
serving inputs, detail/evidence queries are bounded by selected read-model keys,
and control-plane tables are leased with bounded work and terminal evidence.
Runtime workers must not use cold history/audit tables as freshness, fallback,
or queue-maintenance state; cold projections need their own spec and writer.

Provider modules are intentionally sparse. Only domains with real inbound cross-cutting dependencies have `providers.py` today: `ingestion`, `asset_market`, `pulse_lab`, and `watchlist_intel`. Do not add empty provider files.

CLI ops remain a separate operational surface exception: they may construct external clients for explicit operator commands, while service runtime construction stays centralized in `app/runtime/providers_wiring.py`.

## Pulse Agent Runtime

Signal Pulse is the first concrete strategy on the unified Agent Runtime Core.
`domains/pulse_lab/services/agent_routing.py` owns deterministic route policy
(`cex`, `meme`, or `research_only`) and completeness gates. The Pulse worker
turns a factor snapshot into a route, writes an agent run, short-circuits
research-only or hard-blocked rows to an abstain decision, and otherwise calls
the configured `PulseDecisionProvider`.

LiteLLM-specific model calls live only under `integrations/model_execution/`.
Signal Pulse uses one tool-free `pulse_decision` runtime stage, with
deterministic hard-blocks before provider execution. Pulse-specific
orchestration is domain-owned:
`domains/pulse_lab/services/pulse_decision_runtime.py` loads the prompt, builds
the packet-only input contract, assembles request audit hashes, validates cited
evidence refs, and enriches final evidence URLs. The model adapter only
dispatches typed stage specs through `AgentExecutionGateway` and
returns audit envelopes. `app/runtime/provider_wiring/model_execution.py` is the
composition point that creates the domain runtimes and injects concrete LiteLLM
adapters bound to provider protocols.

The audit ledger is PostgreSQL: `pulse_agent_runs` records the final outcome and
route, `pulse_agent_run_steps` records replayable stage inputs/prompts/outputs,
and `pulse_candidates.decision_*` plus `decision_json` are the public decision
source. Signal Pulse public payloads expose `decision`, `factor_snapshot`,
`gate`, and `fact_card`; they do not expose run ids or run-step `stages`.

Narrative Intelligence sits upstream of Pulse decisioning and downstream of
Token Radar discovery. API surfaces may compose Token Radar / Token Case rows
with `NarrativeReadModel`, but they do not run providers, score rows, or write
narrative read models, and Token Radar API composition must pass the formal
nested `target` object through rather than synthesizing top-level target identity
fields for narrative hydration. The active runtime writes only `narrative_admissions`;
admission thresholds come from formal `settings.workers.narrative_admission`
fields, not service-local defaults or carry-forward TTL compatibility. Former
mention-semantic and discussion-digest LLM workers are removed. Public
reads may compose historical ready digest rows with the current
`narrative_admissions` source frontier and expose the delta through
`discussion_digest.currentness`. Fingerprint mismatch alone is not a reason to
blank legacy narrative context, but the digest lookup still requires formal
Token Radar row identity (`target_type` / `target_id`) and treats legacy
`type` / `id` aliases as missing narrative context. Pulse may include a ready discussion digest in
its sealed evidence packet as context, but stale/updating digest prose is not
primary evidence; Pulse hidden/internal candidate state never triggers
narrative workers and never writes legacy narrative semantic/digest tables.
Pulse evidence completeness checks consume the formal sealed
`PulseEvidencePacket`; arbitrary dict/object reflection at this boundary is a
contract failure, not an insufficient-evidence decision.
Pulse evidence market-fact freshness is part of the replay policy owned by
formal `settings.workers.pulse_candidate.evidence_market_freshness_ms` and the
job run's explicit `now_ms`. The evidence builder and evidence source
repository must not keep their own freshness windows or default-current-clock
fallbacks.
Persisting the sealed Pulse evidence packet is also a required single-row
`RETURNING` write: `PulseEvidenceRepository.upsert_packet(...)` must validate
PostgreSQL `cursor.rowcount=1` with a returned packet row before linking
`pulse_agent_runs` to the packet hash.
Pulse timeline context also requires the worker's explicit target `window` and
`scope`; unknown windows or scopes fail before context signatures are computed
instead of being restored to `1h` or `all`.
Pulse admission failure-circuit and timeline-debounce policy is also owned by
formal `settings.workers.pulse_candidate`; the worker passes
`failure_circuit_per_hour` and `timeline_debounce_seconds` explicitly into
`PulseAdmissionPolicy`, whose service method must not keep policy defaults.
Notification rule evaluation is a replayable worker step, not a service-local
clock read. `NotificationWorker` owns the runtime evaluation timestamp and
passes `now_ms` into `NotificationRuleEngine.evaluate(...)`; the rule engine
must not call the current clock or accept missing evaluation time.
Notification rule query policy is also settings-owned: watched-account
activity windows, news high-signal recency, and news high-signal overscan
limits, plus Signal Pulse notification page budget, live in
`settings.notifications`, not `NotificationRuleEngine` module constants.
Notification fact insertion and insert-only delivery enqueue classify
created-vs-existing state from PostgreSQL single-row `cursor.rowcount`
evidence. Missing, boolean, negative, multi-row, or otherwise invalid rowcount
is malformed repository/driver state, not a notification-created,
delivery-created, or existing-row decision.
Notification delivery requeue and claim `RETURNING *` mutations use the same
execution-evidence boundary: optional outcomes are valid only when PostgreSQL
rowcount is 0 with no returned row or 1 with one returned row. Returned-row
presence by itself is not a delivery reactivation or claim contract.
Pulse claim verification uses that sealed packet with the strict `FinalDecision`
model; arbitrary final-decision object reflection is a contract failure before
public write-gate decisions.
Pulse decision stage construction uses the same sealed packet plus
`EvidenceCompletenessGateResult`; JSON context at the integration boundary must
be re-validated into formal models before domain prompt construction.
Pulse stage-output normalization also consumes the formal sealed packet; dict
packet or object-ref compatibility is malformed adapter wiring, not a
normalization input shape.
Pulse deterministic eval cases are stored as JSON audit artefacts, but their
`evidence_packet` payload must be re-validated into `PulseEvidencePacket`
before grading allowed refs; partial dict packets are malformed eval input, not
passing evidence.
Pulse request-audit metadata follows the same rule: audit hashes and trace
packet/gate metadata are derived from `context["evidence_packet"]` after formal
packet validation and from formal `EvidenceCompletenessGateResult` payloads,
never from top-level `evidence_packet_hash` or raw gate-dict compatibility.
Runtime manifest metadata must also carry a non-empty `runtime_version`; empty
runtime-version audit rows are malformed replay metadata, not a default runtime.
Agent run identity fields (`run_id`, `job_id`, model, artifact hash, workflow,
agent) are likewise required before request-audit metadata is built; empty
identity strings are malformed execution lineage.
The runtime manifest's `model.model` and `model.artifact_version_hash` must
match those request-audit identity fields so the runtime hash and run audit
lineage describe the same executable artifact.
`PulseCandidateJobService` must validate claimed-row `job_id`,
`trigger_signature`, `timeline_signature`, and positive `attempt_count` before
building a `run_id` or opening repository sessions; empty identity segments are
malformed queue state, not run-id compatibility input.
`PulseCandidateJobService` must persist `pulse_agent_runs` and run-step
prompt/schema fields from the validated request-audit payload directly. Missing
or mismatched audit identity is a contract failure; the job service must not
rebuild backend, workflow, agent, artifact, prompt/schema, input hash, trace
metadata, runtime version, or runtime hash defaults at the ledger boundary.
Pulse stage audit rows are built only from formal `AgentExecutionResult` and
`AgentExecutionRequestAudit` / `AgentExecutionResultAudit` contracts; malformed
gateway objects fail before run-step audit rows are synthesized.
The Pulse model-execution adapter also validates request-audit trace `run_id`
and stage packet group identity before building `AgentStageSpec`. Missing trace
metadata or missing packet group identity is malformed runtime output, not a
reason to substitute the pipeline `run_id`.
The adapter's workflow identity is likewise explicit: omitted constructor input
uses the canonical Pulse workflow name, but blank or `None` workflow values are
malformed wiring rather than defaultable identity.
Pulse no-start provider backpressure is likewise classified only from formal
`AgentExecutionError.error_class` plus `execution_started=False`; loose
exception audit dicts or alias attributes must not release jobs to provider
cooldown.
Pulse worker hard-timeout cleanup reads `execution_started` only from formal
`AgentExecutionCancelled`; ordinary worker-level cancellations fall back to the
service's `run_started` state. Loose cancellation audit dicts must not decide
whether a timeout is before or after provider execution.

## Asset Profile Facts

Resolved DEX asset profile facts live in `domains/asset_market`, not in Token
Radar scoring snapshots. The runtime profile lane is:

```
resolved/current profile target
  -> token_profile_current_dirty_targets
  -> TokenProfileCurrentWorker
  -> exact persisted profile/evidence sources
  -> token_image_source_dirty_targets for usable logo candidates
  -> TokenImageMirrorWorker
  -> token_image_assets + cache/token-images
  -> token_profile_current.logo_url = /api/token-images/{image_id}
  -> TokenProfileReadModel
  -> /api/token-radar + /api/search/inspect + CLI asset-flow + frontend
```

Only `asset_market` workers and explicit ops commands may call the profile provider.
HTTP handlers, CLI read commands, Token Radar projection, Search read models,
and frontend components read persisted `token_profile_current` through
`TokenProfileReadModel`. Absent current rows can render explicit pending or
unsupported blocks, but present rows must carry formal current-row fields:
`status` is limited to ready/missing/unsupported/error and `source_kind`,
`quality_flags_json`, and `source_payload_json` must be present with the
expected JSON shapes; projection writes and repository upserts use these
formal storage field names directly and do not accept `quality_flags` /
`source_payload` aliases. Public reads must not turn malformed current rows
into pending state, empty flags, or empty source payloads. `asset_profile_refresh`
writes only `asset_profiles`
and profile-current dirty targets when source facts change; ready/missing/error
`asset_profiles.next_refresh_at_ms` and the matching
`asset_profile_refresh_targets.due_at_ms` are computed from the formal
`settings.workers.asset_profile_refresh` refresh cadences by the worker and
passed explicitly into the service/repository boundary. It wakes
`TokenProfileCurrentWorker` but does not own image source admission. The current
profile projection only marks rows
`ready` when the selected source has a usable logo; it also promotes exact
GMGN stream snapshot icons, exact OKX DEX evidence, and Binance CEX profile
source-cache rows already stored in PostgreSQL; it does not use request-time
fallback or symbol-only CEX matching. `cex_tokens` remains identity/routing
only; CEX profile data lives in `cex_token_profiles`. CEX profile source-cache
sync consumes formal mapping-shaped provider profile rows with required
`base_symbol`, `provider`, `symbol`, `logo_url`, `source_ref`, and
mapping-shaped `raw_payload`; object-attribute reflection, missing-provider
defaults, symbol-from-base fallbacks, and empty raw-payload defaults are
malformed provider output rather than compatibility. Source-cache upserts use
optional single-row `RETURNING` evidence: rowcount=0/no row means no routed CEX
token existed, rowcount=1/row means the source-cache row changed or was
refreshed, and malformed rowcount/row mismatches fail before the result is
reported.
Official links and descriptions must be visible without running a narrative
agent; future narrative jobs may consume profile facts, but they do not own
official profile data.

## Market Data Provider Matrix

This matrix is the source of truth for which upstream provider feeds each
market-data lane, which lanes are allowed to write `market_ticks` /
`enriched_events`, and which lanes are read-only. It supersedes any older
phrasing in this doc or `WORKERS.md` that described OKX as a "fallback" to a
GMGN price WebSocket — GMGN's public WebSocket is a *social* ingestion stream,
not a price source. This matrix is canonical; future SDD feature records must
update this section when they change provider ownership.

| Layer | Primary | Fallback | Writes facts | Notes |
|---|---|---|---|---|
| Social ingestion | GMGN DirectWS | none | `events`, `token_intents`, `token_intent_resolutions` | Not a price source |
| Tier 1 price stream | OKX DEX WS | none | `market_ticks(source_tier='tier1_ws')` | `chain_token` only; CEX symbols never enter Tier 1 |
| Tier 2 DEX poll | GMGN OpenAPI REST | OKX DEX REST | `market_ticks(source_tier='tier2_poll')` | No GMGN price WS in the official skills repo |
| Tier 2 CEX poll | Binance USD-M REST | none | `market_ticks(source_tier='tier2_poll')` | CEX WS intentionally out of this pass |
| Event anchor DEX backfill | GMGN OpenAPI REST | OKX DEX REST | `market_ticks`, narrow `enriched_events` lifecycle update; `event_anchor_backfill_jobs` control state | Same `dex_quote_market` provider stack as Tier 2 |
| Event anchor CEX backfill | Binance USD-M REST | none | `market_ticks`, narrow `enriched_events` lifecycle update; `event_anchor_backfill_jobs` control state | Same `cex_market` provider as Tier 2 |
| Frontend `/ws` | latest `market_ticks` read model | none | no facts | `LivePriceGateway` fan-out only; no upstream provider calls |

Consequences for code review:

- Only `MarketTickStreamWorker`, `MarketTickPollWorker`, ingest inline Tier 3
  capture, and `EventAnchorBackfillWorker` may write `market_ticks`. The
  inventory in `WORKERS.md` lists every runtime writer. Their shared append-only
  fact repository validates `RETURNING tick_id` rowcount against returned-row
  presence before classifying created versus duplicate ticks.
- `EventAnchorBackfillWorker` consumes `event_anchor_backfill_jobs`; it must not
  page directly through `enriched_events` as a retry queue. `enriched_events`
  records only event-anchor fact lifecycle: pending, ready, or terminal
  unavailable. Event-anchor job `UPDATE ... RETURNING` claim, cleanup, retry,
  reconcile, done, terminal, and reschedule paths require cursor rowcount to
  match returned rows before worker state is reported.
- `worker_queue_terminal_events` is platform control-plane evidence, not a
  best-effort audit append. Terminal ledger `INSERT ... ON CONFLICT ...
  RETURNING *` writes and operator-action `UPDATE ... RETURNING *` writes
  require PostgreSQL cursor rowcount to be valid 0/1 and match returned-row
  presence before terminal rows, operator payloads, or retry transitions are
  reported.
- `LivePriceGateway` reads the latest `market_ticks` fan-out; it does not
  hold its own upstream WebSocket or REST clients. Its target limit and tick
  TTL are formal worker settings, not runtime constants or constructor
  overrides.
- GMGN's public WebSocket is consumed only by the `collector` social
  ingestion path. Any code that wires it as a price provider is wrong.
- The GMGN DirectWS adapter awaits the collector's async `handle_frame(...)`
  contract directly; sync callback compatibility in this path is a malformed
  runtime boundary, not an adapter feature.

## Generated and reference material

- `docs/generated/{cli-help,ws-protocol,score-versions,db-schema}.md` — regenerated by `make docs-generated`. Score-version paths reflect `domains/token_intel/scoring/`.
- `docs/CONTRACTS.md` — public HTTP / WebSocket / CLI surface contracts.
- `docs/references/` — papers and external API references underpinning algorithm choices.

To find code, prefer `ls src/parallax/domains/<domain>/` over a memorised file list. This file pins the package map; per-file responsibilities live in the code and its tests.

## Public Query Boundary Addendum

Public API and CLI defaults are surface contracts. Runtime helpers, read-model
services, repositories, projection services, and ops repair helpers receive
already-validated query boundaries explicitly. They must not recover malformed
`window`, `scope`, `limit`, or repair-width inputs through product-looking
defaults such as `1h`, `24h`, `all`, or `matched`.

Ops diagnostics follows the same rule: `/api/ops/diagnostics` owns its public
`since_hours`, `window`, and `scope` defaults and validates them before calling
runtime composition. `ops_diagnostics_payload(...)` receives those values as
required inputs so direct runtime callers cannot silently widen or narrow
PostgreSQL diagnostic reads.

Signal Pulse freshness health uses a fixed public health horizon today, but the
same ownership rule applies. `SignalPulseService` and CLI replay/health
commands pass `since_hours` explicitly; `PulseReadRepository.freshness_health`
and `PulseFreshnessHealthService.health` do not define their own 4h fallback.
Signal Pulse public listing follows the same boundary: API/service callers pass
the validated `limit` into `PulseReadRepository.list_candidates(...)`, and the
repository does not own a hidden `50`-row default.

Macro asset correlation follows the same public-query rule. The HTTP route owns
the public `60d` correlation default and validates supported windows before it
loads observations; `build_macro_asset_correlation(...)` receives `window`
explicitly and does not define a service-local default.
Macro public snapshot shaping also preserves the read-model contract: a missing
current snapshot is represented as an explicit `macro_view_snapshot_missing`
data gap, but a present snapshot must carry formal mapping/list-shaped JSON
sections and must not be repaired into empty public sections by the API route.
Macro module pages follow that same boundary when shaping
`macro_module_view_v3`: absent snapshots can render explicit missing module
views, while present `macro_view_snapshots` rows must expose the full formal
section set instead of letting the module builder synthesize empty
feature/scenario/chain/data-gap payloads.

Token Radar projection work width follows the worker-policy version of the
same rule. `TokenRadarProjectionWorker` is the single runtime owner of dirty
claim batch width, rank publication width, lease timing, retry timing, and
lease identity; `TokenRadarProjection` receives `limit`, `rank_limit`,
`lease_ms`, `retry_ms`, and `lease_owner` explicitly and does not define
service-local `100` or synthetic-owner defaults. Projection repository
diagnostic reads over `projection_runs` and `projection_dirty_ranges` likewise
require explicit caller limits; the repository does not own `20`/`50` row
defaults for control-plane status inspection. Ordinary projection offset,
run-ledger, dirty-range enqueue, and finish writes require exactly one
PostgreSQL `cursor.rowcount`, and projection-run start uses RETURNING evidence
rather than fallback readback. Dirty-range claim rows from
`UPDATE projection_dirty_ranges ... RETURNING` must also validate cursor
rowcount against returned rows before work is treated as leased.

Watchlist overview follows the SQL-width version of the same rule. The API
read config owns the public overview window plus source and cluster budgets;
`WatchlistHandleReadService` passes those values explicitly, and
`WatchlistIntelRepository.handle_overview(...)` computes aggregate metrics
separately from a bounded source-event sample before token-resolution fan-out.
