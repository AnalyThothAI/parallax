# Spec - Kappa CQRS Governance Root Fix

**Status**: In Progress
**Date**: 2026-06-12
**Owner**: Codex
**Approved by**: delegated goal
**Approved at**: 2026-06-12
**Related**: `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md`, `docs/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/references/POSTGRES_PERFORMANCE.md`

## Background

The audit recorded that /stocks-radar constructed StocksRadarService during a request and passed runtime.stock_quote_provider into it (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:7, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:11). It also recorded that the service loaded rows from PostgreSQL and then called self.quote_provider.quote(symbol) per symbol (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:12). The current target contract is documented as a DB-only stocks radar endpoint with an explicit unavailable quote state (docs/ARCHITECTURE.md:55, docs/CONTRACTS.md:349).

## Evidence Notes

Macro's CQRS boundary is likewise documented around macro observations, import runs, and projection dirty targets, with rowcount evidence required for writes (`src/parallax/domains/macro_intel/ARCHITECTURE.md:14`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:15`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:18`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:102`). Current repository helpers `_delete_exited_observation_series_rows`, `_insert_observation_series_rows_chunk`, and `_single_rowcount` enforce that read-model writes and single-row accounting do not fall back to missing rowcount evidence (`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1479`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1533`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2219`).

The audit recorded that the `resolution_refresh` manifest was labeled `TARGET_SCOPED_EXPANSION` while already declaring `token_discovery_dirty_lookup_keys` and claiming lookup-key queue rows (`docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:28`, `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:29`, `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:30`, `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:31`). The audit also recorded that `run_resolution_refresh_once` preserved an already-open repository helper path (`docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:47`, `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:48`, `docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:49`).

The audit recorded that the resolution_refresh manifest was labeled TARGET_SCOPED_EXPANSION while already declaring token_discovery_dirty_lookup_keys and claiming lookup-key queue rows (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:28, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:29, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:30, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:31). The audit also recorded that run_resolution_refresh_once preserved an already-open repository helper path (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:47, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:48, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:49).

The audit recorded that notification delivery stale-running cleanup used UPDATE notification_deliveries before each claim and lacked a matching stale-running partial index (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:62, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:66, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:67, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:71). The audit recommendation was to add the index and batch terminalization with LIMIT plus FOR UPDATE SKIP LOCKED (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:80, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:83, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:88).

The audit recorded that Token Radar publication called prune_target_features and prune_edges inside the publish attempt (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:90, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:94, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:95). It also recorded that Pulse handle filtering expanded source_event_ids_json and evidence_event_ids_json through jsonb_array_elements_text (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:108, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:112, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:113).

Follow-up review found another Pulse read-path boundary leak: /api/signal-lab/pulse injected scheduler liveness from _worker_running(runtime, "pulse_candidate") into SignalPulseService.pulse(...), and the public payload exposed agent_worker_running (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:149). The target contract is that SignalPulseHealth is persisted summary/freshness state only (src/parallax/app/surfaces/api/schemas.py:497), with agent_worker_running absent from OpenAPI and frontend contracts (tests/contract/test_openapi_drift.py:180), and scheduler/worker liveness kept in status or ops diagnostics (docs/CONTRACTS.md:638).

Follow-up review also found that /api/news/sources/status derived supported provider types from runtime.providers.news_intel.feed_client and the private provider registry shape (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:168). The target contract is that News source status combines persisted source rows with the static runtime provider-type contract, not a per-process provider object (docs/CONTRACTS.md:222), and architecture tests now reject runtime provider object access in that route (tests/architecture/test_api_read_paths_provider_free.py:250).

The same root cause remained in News provider-contract validation: NewsFetchWorker and runtime status health still probed the feed client or its private registry to learn supported provider types (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:182). The target contract is that all News provider contract validation uses the same static platform provider-type contract and schema constraint values; provider clients fetch observations only (docs/WORKERS.md:807, docs/WORKERS.md:811, src/parallax/domains/news_intel/ARCHITECTURE.md:246).

Follow-up review then found the schema side of the same News provider contract still had a fallback from missing repository schema introspection to the Python PROVIDER_TYPES enum (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:199). The target contract is that News provider-contract status validates configured sources against the live news_sources database constraint plus static runtime-supported types, with no provider object or enum fallback (docs/CONTRACTS.md:142, docs/WORKERS.md:347).

Follow-up review also found NewsItemProcessWorker still built agent-admission context with worker-memory fallbacks when load_agent_admission_contexts returned incomplete rows (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:212, src/parallax/domains/news_intel/runtime/news_item_process_worker.py:35, src/parallax/domains/news_intel/runtime/news_item_process_worker.py:194, tests/architecture/test_news_intel_kiss_simplification.py:123, tests/unit/domains/news_intel/test_news_workers.py:2053). The target contract is that item-process writes deterministic facts, reads the admission context back through the News repository in the same transaction, and fails closed if that repository contract is missing or incomplete.
Projection workers document RepositorySession.transaction as the transaction boundary for claimed work and read-model rewrites (src/parallax/domains/news_intel/ARCHITECTURE.md:127, docs/WORKERS.md:624).

Follow-up review found the same claim-field fallback one layer earlier in
NewsItemProcessWorker: item processing completion and failure paths used
claimed processing_attempts and processing_lease_owner for CAS, but the
runtime helper converted missing or invalid processing_attempts to zero and
missing processing_lease_owner to an empty string. The target contract is that
claimed News item rows expose a positive processing_attempts and non-empty
processing_lease_owner before deterministic writes, retry/terminal failure,
or downstream dirty enqueue; malformed claim rows fail before state-machine
branching
(src/parallax/domains/news_intel/runtime/news_item_process_worker.py:35,
src/parallax/domains/news_intel/runtime/news_item_process_worker.py:88,
src/parallax/domains/news_intel/runtime/news_item_process_worker.py:89,
src/parallax/domains/news_intel/runtime/news_item_process_worker.py:376,
src/parallax/domains/news_intel/runtime/news_item_process_worker.py:388,
tests/unit/domains/news_intel/test_news_workers.py:692,
tests/unit/domains/news_intel/test_news_workers.py:720,
tests/architecture/test_news_intel_kiss_simplification.py:141,
tests/architecture/test_news_intel_kiss_simplification.py:159,
tests/architecture/test_news_intel_kiss_simplification.py:161).

Follow-up review found the same claim-field gap across dirty completion keys:
many queues already required claimed-row attempt_count, but still restored
missing lease_owner to an empty string before done/error/reschedule or
terminal SQL. The target contract is that dirty completion keys preserve both
claimed-row fields: positive attempt_count and non-empty lease_owner; missing
owners fail before rank-source work, source projection, or queue SQL.
Architecture coverage rejects owner-default restoration tokens and requires
direct lease-owner readers, with a row-indexed lease owner for the event-anchor
worker special case
(tests/architecture/test_runtime_worker_constraint_hard_cut.py:1763,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1764,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1765,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1775,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1778,
src/parallax/domains/token_intel/services/token_radar_projection.py:1296,
src/parallax/domains/token_intel/services/token_radar_projection.py:1297,
src/parallax/domains/token_intel/services/token_radar_projection.py:1339,
src/parallax/domains/token_intel/services/token_radar_projection.py:1340,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:838,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:839).

Follow-up review found that asset_profile_refresh source-cache scheduling
still needed one formal runtime owner; asset_profiles is documented as the
provider source cache and its next_refresh_at_ms must match refresh-target
due_at_ms reschedules (src/parallax/domains/asset_market/ARCHITECTURE.md:27).
AssetProfileRefreshWorkerSettings now exposes ready/missing/error refresh
fields as formal settings (src/parallax/platform/config/settings.py:990,
src/parallax/platform/config/settings.py:994,
src/parallax/platform/config/settings.py:995,
src/parallax/platform/config/settings.py:996).
AssetProfileRefreshWorker owns the runtime computation and passes the same
next-refresh value to refresh-target due_at_ms reschedules
(src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:22,
src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:132,
src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:167,
src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:195,
src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:212).
The service/repository boundary requires explicit next_refresh_at_ms instead
of owning hidden refresh constants
(src/parallax/domains/asset_market/services/asset_profile_refresh.py:28,
src/parallax/domains/asset_market/services/asset_profile_refresh.py:90,
src/parallax/domains/asset_market/repositories/asset_profile_repository.py:40,
src/parallax/domains/asset_market/repositories/asset_profile_repository.py:72).

Follow-up review found the same rowcount evidence gap in
asset_profile_refresh_targets completion accounting: reschedule/error paths
still had default zero-target accounting through rowcount fallback helpers. The
target contract is that
reschedule/error changed-row counts use _cursor_rowcount(cursor) and fail as
asset_profile_refresh_target_rowcount_required /
asset_profile_refresh_target_rowcount_invalid before reporting zero changed
refresh targets
(src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:57,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1611,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1612,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:224,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:277,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:316,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:318,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:320).

Follow-up review found the same rowcount evidence gap in
token_profile_current_dirty_targets completion accounting: done/error paths
reported changed-row counts after queue CAS mutations but could still restore
missing rowcount evidence to zero. The target contract is that done/error
changed-row counts use _cursor_rowcount(cursor) and fail as
token_profile_current_dirty_target_rowcount_required /
token_profile_current_dirty_target_rowcount_invalid before reporting zero
changed profile-current targets
(src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:228,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:238,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:280,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:295,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:489,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:493,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:495,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:497,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1636,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1637,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1638,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1639).

Follow-up review found the same rowcount evidence gap in
market_tick_current_dirty_targets completion accounting: done/error paths
reported changed-row counts after queue CAS mutations but could still restore
missing rowcount evidence to zero. The target contract is that done/error
changed-row counts use _cursor_rowcount(cursor) and fail as
market_tick_current_dirty_target_rowcount_required /
market_tick_current_dirty_target_rowcount_invalid before reporting zero
changed market-current targets
(src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:168,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:178,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:216,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:231,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:387,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:391,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:393,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:395,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1111,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1112,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1116,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1119).

Follow-up review found the same rowcount evidence gap in
token_image_source_dirty_targets completion accounting: done/error paths
reported changed-row counts after image-source queue CAS mutations but could
still restore missing rowcount evidence to zero. The target contract is that
done/error changed-row counts use _cursor_rowcount(cursor) and fail as
token_image_source_dirty_target_rowcount_required /
token_image_source_dirty_target_rowcount_invalid before reporting zero changed
image-source targets
(src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:346,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:362,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:400,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:413,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:655,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:659,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:661,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:144,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:148,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:152,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:157,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1726,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1745,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1746,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1747,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1748,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1749,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1750,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1751).

Follow-up review found the same write-evidence gap at the token fact root:
the token evidence and token intent insert paths now use RETURNING * with
required rowcount=1 before returning written facts
(src/parallax/domains/token_intel/repositories/token_evidence_repository.py:18,
src/parallax/domains/token_intel/repositories/token_evidence_repository.py:41,
src/parallax/domains/token_intel/repositories/token_evidence_repository.py:46,
src/parallax/domains/token_intel/repositories/token_intent_repository.py:18,
src/parallax/domains/token_intel/repositories/token_intent_repository.py:41,
src/parallax/domains/token_intel/repositories/token_intent_repository.py:46).
Event-scoped token evidence/intent deletes require real non-negative rowcount,
token intent evidence links accept only explicit rowcount 0/1, lookup-key
replacement upserts require rowcount=1 after a real delete rowcount, and
resolution supersede/upsert requires rowcount evidence before returning current
resolution facts
(src/parallax/domains/token_intel/repositories/token_evidence_repository.py:54,
src/parallax/domains/token_intel/repositories/token_intent_repository.py:47,
src/parallax/domains/token_intel/repositories/token_intent_repository.py:108,
src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py:12,
src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py:23,
src/parallax/domains/token_intel/repositories/token_intent_lookup_repository.py:38,
src/parallax/domains/token_intel/repositories/intent_resolution_repository.py:15,
src/parallax/domains/token_intel/repositories/intent_resolution_repository.py:27,
src/parallax/domains/token_intel/repositories/intent_resolution_repository.py:39,
src/parallax/domains/token_intel/repositories/intent_resolution_repository.py:78).
Unit coverage now exercises missing/invalid rowcount, required single-row
0/2 failures, optional link 0/1 evidence, and supersede-update rowcount
(tests/unit/domains/token_intel/test_token_fact_repositories.py:110,
tests/unit/domains/token_intel/test_token_fact_repositories.py:163,
tests/unit/domains/token_intel/test_token_fact_repositories.py:211,
tests/unit/domains/token_intel/test_token_fact_repositories.py:223,
tests/unit/domains/token_intel/test_token_fact_repositories.py:238,
tests/unit/domains/token_intel/test_token_fact_repositories.py:256).
The architecture guard rejects fallback readback and rowcount-default
compatibility for these token fact writers
(tests/architecture/test_runtime_worker_constraint_hard_cut.py:709,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:716,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:723).

Follow-up review found the same rowcount evidence gap in
token_capture_tier_dirty_targets write accounting: rank-set dirty enqueue and
done paths reported changed-row counts after queue mutations but could still
restore missing rowcount evidence to zero. The target contract is that
enqueue/done changed-row counts use _cursor_rowcount(cursor) and fail as
token_capture_tier_dirty_target_rowcount_required /
token_capture_tier_dirty_target_rowcount_invalid before reporting zero changed
capture-tier dirty targets
(src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:15,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:37,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:90,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:109,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:156,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:166,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:210,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:214,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:216,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:218,
tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py:68,
tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py:72,
tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py:83,
tests/unit/domains/asset_market/test_token_capture_tier_dirty_targets.py:87,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1384,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1385,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1386,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1387).

Follow-up review found the same rowcount evidence gap in the serving/control
projection itself: demote_hot_rows_outside_rank_set returns the number of hot
tier rows demoted outside the active rank set. The
target contract is that demotion changed-row counts use _cursor_rowcount(cursor)
and fail as token_capture_tier_repository_rowcount_required /
token_capture_tier_repository_rowcount_invalid before reporting zero demoted
rows
(src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:138,
src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:165,
src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:205,
src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:209,
src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:211,
src/parallax/domains/asset_market/repositories/token_capture_tier_repository.py:213,
tests/unit/test_token_capture_tier_repository.py:132,
tests/unit/test_token_capture_tier_repository.py:136,
tests/unit/test_token_capture_tier_repository.py:144,
tests/unit/test_token_capture_tier_repository.py:177,
tests/unit/test_token_capture_tier_repository.py:186,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1126,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1135,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1136,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1140,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1141,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1142,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1143).

Follow-up review found the same current-row changed evidence gap in
asset_identity_current: recompute_current_identity turns the changed
boolean from _upsert_current_identity into rows_written, and the current
identity write uses RETURNING true AS changed. The target contract is that
asset_identity_current changed booleans
require PostgreSQL cursor.rowcount, only accept 0/1, and match returned-row
presence before identity recompute rows_written is reported
(src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:266,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:267,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:270,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:272,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:275,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:298,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:313,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:314,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:298,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:313,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:314,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:368,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:370,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:372,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:374,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:380,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:382,
src/parallax/domains/asset_market/repositories/identity_evidence_repository.py:384,
tests/unit/test_asset_identity_repository.py:104,
tests/unit/test_asset_identity_repository.py:118,
tests/unit/test_asset_identity_repository.py:143,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1491,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1504,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1516,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1521,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1522,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1524,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1525).

Follow-up review found that PulseAdmissionPolicy still needed a strict caller
owned policy contract. Its classifier now requires explicit
recent_failure_count, failure_circuit_per_hour, and
timeline_debounce_seconds inputs (src/parallax/domains/pulse_lab/services/pulse_admission_policy.py:19,
src/parallax/domains/pulse_lab/services/pulse_admission_policy.py:29,
src/parallax/domains/pulse_lab/services/pulse_admission_policy.py:30,
src/parallax/domains/pulse_lab/services/pulse_admission_policy.py:31).
PulseCandidateWorker reads formal failure-circuit and timeline-debounce
settings and passes them into the policy call
(src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:63,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:98,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:99,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:491,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:494).
timeline_debounce_seconds is exposed in the formal Pulse candidate worker
settings (src/parallax/platform/config/settings.py:1132).

Follow-up review found that notification rule evaluation still needed an
explicit worker-owned clock contract. NotificationRuleEngine now has an
evaluate method that requires now_ms: int and derives the evaluation
timestamp only from that input
(src/parallax/domains/notifications/services/notification_rules.py:29,
src/parallax/domains/notifications/services/notification_rules.py:45,
src/parallax/domains/notifications/services/notification_rules.py:46).
NotificationWorker computes the runtime timestamp and passes it into
rule_engine.evaluate(now_ms=now_ms)
(src/parallax/domains/notifications/runtime/notification_worker.py:31,
src/parallax/domains/notifications/runtime/notification_worker.py:75,
src/parallax/domains/notifications/runtime/notification_worker.py:76,
src/parallax/domains/notifications/runtime/notification_worker.py:88).
The notification architecture guard rejects service-local wall-clock fallback
tokens such as import time, optional now_ms, and _now_ms()
(tests/architecture/test_notifications_hard_cut.py:187,
tests/architecture/test_notifications_hard_cut.py:188,
tests/architecture/test_notifications_hard_cut.py:189,
tests/architecture/test_notifications_hard_cut.py:190,
tests/architecture/test_notifications_hard_cut.py:193,
tests/architecture/test_notifications_hard_cut.py:194,
tests/architecture/test_notifications_hard_cut.py:195,
tests/architecture/test_notifications_hard_cut.py:196).

Follow-up review found the same formal-policy gap in external delivery retry
budgets. NotificationWorker writes external delivery control rows with
max_attempts=self.delivery_max_attempts, so the constructor must require that
value explicitly and the runtime factory must pass
workers.notification_delivery.max_attempts
(src/parallax/domains/notifications/runtime/notification_worker.py:31,
src/parallax/domains/notifications/runtime/notification_worker.py:43,
src/parallax/domains/notifications/runtime/notification_worker.py:55,
src/parallax/domains/notifications/runtime/notification_worker.py:168,
src/parallax/app/runtime/worker_factories/notifications.py:44).
The notification architecture guard rejects delivery_max_attempts: int = and
requires the factory to pass the formal delivery setting
(tests/architecture/test_notifications_hard_cut.py:117,
tests/architecture/test_notifications_hard_cut.py:129,
tests/architecture/test_notifications_hard_cut.py:132).

Follow-up review found that notification query windows and News overscan
policy also needed formal settings ownership. NotificationsConfig now owns
candidate_limit, watched_activity_window_ms,
news_high_signal_recency_window_ms, news_high_signal_query_min_limit, and
news_high_signal_query_multiplier
(src/parallax/platform/config/settings.py:489,
src/parallax/platform/config/settings.py:493,
src/parallax/platform/config/settings.py:494,
src/parallax/platform/config/settings.py:495,
src/parallax/platform/config/settings.py:496,
src/parallax/platform/config/settings.py:497).
The notification rule engine reads those settings for watched activity
recency, News high-signal recency, and News high-signal query width
(src/parallax/domains/notifications/services/notification_rules.py:62,
src/parallax/domains/notifications/services/notification_rules.py:291,
src/parallax/domains/notifications/services/notification_rules.py:388,
src/parallax/domains/notifications/services/notification_rules.py:389).
The architecture guard rejects service-local policy constants such as
WATCHED_ACTIVITY_WINDOW_MS, NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT,
NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER, and NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS
(tests/architecture/test_notifications_hard_cut.py:194,
tests/architecture/test_notifications_hard_cut.py:198,
tests/architecture/test_notifications_hard_cut.py:199,
tests/architecture/test_notifications_hard_cut.py:200,
tests/architecture/test_notifications_hard_cut.py:201,
tests/architecture/test_notifications_hard_cut.py:204,
tests/architecture/test_notifications_hard_cut.py:205,
tests/architecture/test_notifications_hard_cut.py:206,
tests/architecture/test_notifications_hard_cut.py:207,
tests/architecture/test_notifications_hard_cut.py:208,
tests/architecture/test_notifications_hard_cut.py:209,
tests/architecture/test_notifications_hard_cut.py:210,
tests/architecture/test_notifications_hard_cut.py:211,
tests/architecture/test_notifications_hard_cut.py:212).

Follow-up review found the same query-budget ownership issue in Signal Pulse
notification pagination. NotificationsConfig now owns
signal_pulse_max_pages
(src/parallax/platform/config/settings.py:489,
src/parallax/platform/config/settings.py:498,
src/parallax/platform/config/settings.py:1782).
The rule engine uses signal_pulse_max_pages only to derive the per-scope/status
candidate budget passed to the dedicated Signal Pulse notification candidate
reader
(src/parallax/domains/notifications/services/notification_rules.py:181,
src/parallax/domains/notifications/services/notification_rules.py:185).
That reader materializes scopes/statuses as PostgreSQL keysets and applies a
bucket window rank
(src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:97,
src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:113,
src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:119,
src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:127,
src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:128).
The architecture guard rejects the old service-local page constant and
public-list cursor pagination, and requires the formal settings field plus
dedicated reader call
(tests/architecture/test_notifications_hard_cut.py:215,
tests/architecture/test_notifications_hard_cut.py:223,
tests/architecture/test_notifications_hard_cut.py:224,
tests/architecture/test_notifications_hard_cut.py:225,
tests/architecture/test_notifications_hard_cut.py:226,
tests/architecture/test_notifications_hard_cut.py:227,
tests/architecture/test_notifications_hard_cut.py:228,
tests/architecture/test_notifications_hard_cut.py:229,
tests/architecture/test_notifications_hard_cut.py:230,
tests/architecture/test_notifications_hard_cut.py:231,
tests/architecture/test_notifications_hard_cut.py:232).

Follow-up review found the next field in the same dirty completion CAS key still
had a compatibility fallback: completion helpers restored missing payload_hash
to an empty string before done/error/reschedule SQL, and Token Radar projection
could start target/source work with empty payload completion keys. The target
contract is that dirty completion keys preserve claimed-row payload_hash as
well as attempt_count and lease_owner; missing payload hashes fail before
rank-source work, source projection, or queue SQL. The current implementation
routes projection claim keys through _claim_payload_hash(claim), and
architecture coverage requires direct payload-hash readers while rejecting
payload-hash default restoration tokens
(`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2169`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2190`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2191`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2192`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2202`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1289`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1290`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1291`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1332`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1387`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1389`,
`src/parallax/domains/token_intel/services/token_radar_projection.py:1394`).

Follow-up review found Token Image Source dirty completion still had a target-key
compatibility fallback after the shared CAS fields were hardened: missing
source_url_hash could be rederived from source_url before done/error
completion. The target contract is that completion keys use the exact
claimed-row source_url_hash; missing source hashes fail before SQL and must not
be restored by hashing the claimed source_url. Unit coverage asserts the
missing field produces a KeyError cause before SQL, while the architecture
guard rejects the old fallback tokens and requires direct claim["source_url_hash"]
(src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:528,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:530,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:531,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:637,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:127,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:132,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:140,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2100,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2101,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2105).

Follow-up review found the same payload fallback one layer downstream in the
Pulse Candidate worker: exit suppression for a missing current Radar row wrote
trigger_signature as an empty string when the dirty
claim omitted payload_hash. The target contract is that exit-suppression audit
state uses the claimed dirty-trigger payload_hash directly and fails before
admission writes when the claim payload is malformed. Unit coverage asserts
dirty_triggers_failed, no admission writes, and
pulse_trigger_dirty_claim_payload_hash_required; architecture coverage rejects
payload-hash default restoration and requires direct claim["payload_hash"]
(src/parallax/domains/pulse_lab/ARCHITECTURE.md:181,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:850,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:852,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:896,
tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py:160,
tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py:196,
tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py:200,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1849,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1809,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1814,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:850,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:852,
src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:896).

Follow-up review found Token Radar downstream fan-out still compared previous
and current row payload hashes through empty-string fallbacks before deciding
whether to enqueue Pulse, Narrative Admission, or Token Profile Current dirty
work. The target contract is that previous/current row payload_hash values are
required read-model signatures; missing values fail before skip decisions or
target-feature row hydration instead of being compared as equal empty signatures.
Architecture coverage requires _rank_change_payload_hash(previous) and
_rank_change_payload_hash(row)
(src/parallax/domains/token_intel/services/token_radar_projection.py:895,
src/parallax/domains/token_intel/services/token_radar_projection.py:942,
src/parallax/domains/token_intel/services/token_radar_projection.py:987,
src/parallax/domains/token_intel/services/token_radar_projection.py:1404,
src/parallax/domains/token_intel/services/token_radar_projection.py:1406,
src/parallax/domains/token_intel/services/token_radar_projection.py:1411,
src/parallax/domains/token_intel/services/token_radar_projection.py:2567,
tests/unit/test_token_radar_projection.py:1019,
tests/unit/test_token_radar_projection.py:1040,
tests/unit/test_token_radar_projection.py:1049,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1822,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1823,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1824,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1828,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1829).

Follow-up review found the same Token Radar identity leak one hop earlier in
dirty completion claims: target dirty completion still accepted alias
target_type / target_id, while source dirty completion still accepted
defaulted projection_version or alias event_id, target_type, and
target_id. The target contract is that target dirty completion keys require
formal target_type_key and identity_id, source dirty completion keys require
formal projection_version, source_event_id, target_type_key, and
identity_id, and alias mapping is only allowed before enqueue, not after
claim when building done/error CAS keys
(src/parallax/domains/token_intel/services/token_radar_projection.py:1290,
src/parallax/domains/token_intel/services/token_radar_projection.py:1292,
src/parallax/domains/token_intel/services/token_radar_projection.py:1320,
src/parallax/domains/token_intel/services/token_radar_projection.py:1323,
src/parallax/domains/token_intel/services/token_radar_projection.py:1328,
src/parallax/domains/token_intel/services/token_radar_projection.py:1333,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:834,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:856,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:329,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1841,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1842,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1843,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1844,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1847,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1848,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1849,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1850,
src/parallax/domains/token_intel/ARCHITECTURE.md:50,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1853,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1855,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1856,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1857).

Follow-up review then found the architecture guard still carried repository
upward-import exceptions for deterministic leaf primitives. The target contract
is that News canonical identity, Narrative fingerprints, and Token Radar payload
hash primitives live under the cited domain type leaf files, while the
repository/query guard rejects .services., .runtime., and .read_models.
imports without an
allowlist (src/parallax/domains/news_intel/ARCHITECTURE.md:80,
src/parallax/domains/narrative_intel/ARCHITECTURE.md:54,
src/parallax/domains/token_intel/ARCHITECTURE.md:63,
src/parallax/domains/news_intel/types/news_canonical_identity.py:34,
src/parallax/domains/narrative_intel/types/fingerprints.py:14,
src/parallax/domains/token_intel/types/token_radar_payload_hash.py:14,
tests/architecture/test_src_domain_architecture.py:327).

Follow-up review recorded the same optional-repository root in Token Case CEX detail reads: TokenCaseService._cex_detail(...) treated missing cex_detail_snapshots support as no detail, and Search Inspect did not pass the snapshot repository into the token-result dossier path (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:312). The same root-cause note records the target contract: CexToken token dossiers read persisted cex_detail_snapshots; absent rows can produce structured missing detail, while absent repository support fails closed (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:314).

Follow-up review then found the same pattern in Token Case market-live reads: _latest_market_tick(...) treated missing latest_market_tick repository support as no market snapshot (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:325). The target contract is that Token Case and Search Inspect market-live blocks read persisted current tick state; absent rows can produce structured status value missing (docs/CONTRACTS.md:570), while absent repository support fails closed (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:327).

Follow-up review also found the same optional-contract pattern in Pulse dirty-trigger admission: _call_optional(repos.pulse_jobs, "job_for_candidate", ...) and _call_optional(repos.pulse_admission, "edge_state_by_candidate", ...) treated missing control-plane reads as empty state, while recent_target_failure_count, pending_agent_job_count, pending_agent_job_count_for_window_scope, and pulse_trigger_dirty_targets.queue_depth returned 0 when methods were absent (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:337). The target contract is that Pulse dirty-trigger admission, capacity, edge-state, and queue-depth reads use formal PostgreSQL control-plane repositories; missing repository support fails dirty triggers for retry instead of becoming silent empty state (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:339).

Follow-up review found the same optional-session root in Notification Rule writes: NotificationWorker entered a nullcontext() when unit_of_work was absent and then manually committed through the notification repository connection (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:363). The target contract is that the notification rule worker writes notifications facts and notification_deliveries control rows inside the worker-session Unit of Work; missing UoW support fails before writes instead of becoming a compatibility commit path (docs/WORKERS.md:210, docs/WORKERS.md:301, docs/WORKERS.md:302, docs/WORKERS.md:303).

Follow-up review found the same optional-session root in `import_macrodata_bundle(...)`: the previous path used `_unit_of_work(repos)` and raw connection-transaction fallback for Macro offline replay/seed, while `write_macrodata_bundle_import(...)` hid missing `require_transaction` behind a helper (`docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:377`). The target contract is now explicit: offline replay writes macro observations, import runs, and projection dirty targets through `RepositorySession.unit_of_work` and `require_transaction`, and must not fall back to raw `conn.transaction` or manual commits (`src/parallax/domains/macro_intel/ARCHITECTURE.md:205`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:206`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:207`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:208`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py:75`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py:146`).

Follow-up review found the same optional-session root in Pulse agent job writes: PulseCandidateJobService.run_job(...) previously wrapped write blocks in _transaction(repos.conn), which could use raw connection transactions or return nullcontext() when transaction support was absent (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:394, docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:403). The target contract is that Pulse agent run/step/eval/candidate/playbook/admission/job terminal writes use RepositorySession.transaction and fail before writes when session transaction support is missing (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:396, src/parallax/domains/pulse_lab/ARCHITECTURE.md:99, src/parallax/domains/pulse_lab/ARCHITECTURE.md:100, src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py:151).

Follow-up review found the same optional-session root in News projection writes: NewsPageProjectionWorker and NewsSourceQualityProjectionWorker previously wrapped claim/write blocks in _transaction(repos.conn), which could use raw connection transactions or return nullcontext() when transaction support was absent (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:410, docs/WORKER_FLOW.md:165). The target contract is that News page/source-quality dirty claims, read-model writes, downstream dirty enqueue, and done/error state updates use RepositorySession.transaction and fail before claim/write when session transaction support is missing (src/parallax/domains/news_intel/ARCHITECTURE.md:127, src/parallax/domains/news_intel/ARCHITECTURE.md:128, docs/WORKERS.md:624, src/parallax/domains/news_intel/runtime/news_page_projection_worker.py:45, src/parallax/domains/news_intel/runtime/news_source_quality_projection_worker.py:45).

Follow-up review found the same raw-connection transaction root in the outer Pulse dirty-trigger worker: PulseCandidateWorker still wrapped dirty-trigger claim, admission/edge/public visibility writes, job enqueue, and dirty-target done/error updates in _transaction(repos.conn) (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:426, src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:162, src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:185, src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:269, src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py:481). The target contract is that PulseCandidateWorker uses RepositorySession.transaction and fails before dirty target claim when session transaction support is missing (src/parallax/domains/pulse_lab/ARCHITECTURE.md:144, src/parallax/domains/pulse_lab/ARCHITECTURE.md:146, docs/WORKERS.md:435, docs/WORKERS.md:436, tests/architecture/test_pulse_no_compat.py:209, tests/unit/domains/pulse_lab/test_pulse_candidate_worker_dirty_triggers.py:30).

Follow-up review found the same raw-connection transaction root in News runtime write workers: NewsFetchWorker, NewsItemProcessWorker, and NewsItemBriefWorker previously used direct raw connection transactions for source reconcile/claim, provider item/canonical item writes, deterministic item fact writes, agent admission/current brief writes, projection dirty enqueue, and failure state (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:441, src/parallax/domains/news_intel/runtime/news_fetch_worker.py:63, src/parallax/domains/news_intel/runtime/news_item_process_worker.py:56, src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:50). The target contract is that all three News writer workers use RepositorySession.transaction and fail before reconcile, claim, or write when session transaction support is missing (src/parallax/domains/news_intel/ARCHITECTURE.md:160, src/parallax/domains/news_intel/ARCHITECTURE.md:162, docs/WORKERS.md:652, docs/WORKERS.md:654, tests/architecture/test_news_intel_kiss_simplification.py:200, tests/unit/domains/news_intel/test_news_workers.py:110, tests/unit/domains/news_intel/test_news_workers.py:587, tests/unit/domains/news_intel/test_news_item_brief_worker.py:54).

Follow-up review found the same malformed-ledger fallback inside
NewsItemBriefWorker: reusable completed/failed news_item_agent_runs were
allowed to lose run_id and either restore empty current-brief identity or fall
through to another model call. The target contract is that
the run row's run_id is required before completed-current restore,
failed-current restore, or invalid-completed-run audit; missing identity fails
the dirty target as news_item_brief_run_id_required:{reason}
(src/parallax/domains/news_intel/ARCHITECTURE.md:83,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:50,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:367,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:716,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:883,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:894,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:932,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:937,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:941,
src/parallax/domains/news_intel/runtime/news_item_brief_worker.py:944,
tests/unit/domains/news_intel/test_news_item_brief_worker.py:351,
tests/unit/domains/news_intel/test_news_item_brief_worker.py:431,
tests/architecture/test_news_intel_kiss_simplification.py:842,
tests/architecture/test_news_intel_kiss_simplification.py:843).

Follow-up review found the same optional-session root in Event Anchor stale cleanup: EventAnchorBackfillWorker._expire_stale_jobs previously ran from _worker_session, called expire_stale, and then used _commit_if_supported / commit() instead of requiring unit_of_work before terminalizing event_anchor_backfill_jobs and matching enriched_events lifecycle state (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:455, docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:457). The target contract is that stale cleanup enters _transaction_session / worker-session unit_of_work before expire_stale and terminal writes; missing session support fails before cleanup writes, guarded by source and tests (src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:280, src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:281, src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:282, src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:395, src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:396, tests/architecture/test_runtime_worker_constraint_hard_cut.py:240, tests/unit/test_event_anchor_backfill_worker.py:118, src/parallax/domains/asset_market/ARCHITECTURE.md:21, docs/WORKERS.md:179, docs/WORKERS.md:392).

Follow-up review found the same manual-commit root in Token Capture Tier projection: TokenCaptureTierWorker._project_once(...) could claim token_capture_tier_dirty_targets with commit=True, while project_once(..., commit: bool = True) still had _commit_if_supported(repos) and manual repos.conn.commit() / repos.commit() probing after token_capture_tier writes (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:470). The target contract is that _project_once(...) enters repos.transaction() before claim_due, project_once(...) calls repos.require_transaction(operation="token_capture_tier_projection"), and tests forbid _commit_if_supported, commit=True, commit: bool, and manual commit() compatibility (src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:73, src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:74, src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py:106, tests/architecture/test_runtime_worker_constraint_hard_cut.py:276, tests/architecture/test_runtime_worker_constraint_hard_cut.py:285, tests/architecture/test_runtime_worker_constraint_hard_cut.py:286, tests/architecture/test_runtime_worker_constraint_hard_cut.py:287, tests/architecture/test_runtime_worker_constraint_hard_cut.py:288, tests/unit/test_token_capture_tier_worker.py:247, tests/unit/test_token_capture_tier_worker.py:259).

Follow-up review found the same optional connection-transaction root one layer lower in Event Anchor repository terminal paths: EventAnchorBackfillJobRepository.expire_stale(...), mark_terminal(...), and _transaction(self._conn) still allowed old _transaction(conn) / nullcontext() behavior when conn.transaction() was absent (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:486, docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:488, docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:490). The target contract is that expire_stale(...) and mark_terminal(...) enter _transaction(self._conn), _transaction(conn) raises RuntimeError("event_anchor_repository_transaction_required") when no callable transaction exists, architecture tests reject nullcontext fallback, and the unit fake proves missing transaction leaves conn.sql empty (src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:120, src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:206, src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:602, src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:606, src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:608, tests/architecture/test_runtime_worker_constraint_hard_cut.py:337, tests/architecture/test_runtime_worker_constraint_hard_cut.py:355, tests/architecture/test_runtime_worker_constraint_hard_cut.py:356, tests/architecture/test_runtime_worker_constraint_hard_cut.py:357, tests/unit/test_event_anchor_backfill_job_repository.py:337, tests/unit/test_event_anchor_backfill_job_repository.py:345).

Follow-up review found the same optional connection-transaction root in the platform Queue Terminal operator path: resolve_terminal_event(...) used SELECT ... FOR UPDATE but _transaction(conn) fell back to nullcontext() and retained a manual conn.commit() branch when the connection omitted transaction() (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:501). The target contract is that operator retry/archive/quarantine resolution over worker_queue_terminal_events enters a callable connection transaction, raises RuntimeError("queue_terminal_transaction_required") before any SQL when absent, and never treats row-locking terminal resolution as a no-transaction compatibility path (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:509, src/parallax/platform/db/queue_terminal.py:224, src/parallax/platform/db/queue_terminal.py:237, src/parallax/platform/db/queue_terminal.py:267, src/parallax/platform/db/queue_terminal.py:376, tests/architecture/test_runtime_worker_constraint_hard_cut.py:282, tests/unit/test_queue_terminal.py:376).

Follow-up review found the same optional connection-transaction root in DiscoveryRepository.terminalize_lookup_claims(...): it deleted claimed token_discovery_dirty_lookup_keys, wrote worker_queue_terminal_events, fell back to nullcontext() when _transaction(self.conn) had no conn.transaction(), and retained a manual self.conn.commit() branch (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:516). The target contract is that discovery terminalization raises RuntimeError("discovery_repository_transaction_required") before delete or ledger SQL when the connection transaction contract is missing, and otherwise keeps delete-returning plus terminal-ledger insert inside _transaction(self.conn) (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:524, src/parallax/domains/asset_market/repositories/discovery_repository.py:317, src/parallax/domains/asset_market/repositories/discovery_repository.py:331, src/parallax/domains/asset_market/repositories/discovery_repository.py:341, src/parallax/domains/asset_market/repositories/discovery_repository.py:728, src/parallax/domains/asset_market/repositories/discovery_repository.py:732, src/parallax/domains/asset_market/repositories/discovery_repository.py:734, tests/architecture/test_runtime_worker_constraint_hard_cut.py:500, tests/architecture/test_runtime_worker_constraint_hard_cut.py:524, tests/architecture/test_runtime_worker_constraint_hard_cut.py:526, tests/unit/test_discovery_repository.py:204, tests/unit/test_discovery_repository.py:205).

Follow-up review found the same rowcount evidence gap in Discovery lookup queue
write accounting: lookup enqueue, done, and reschedule paths mutate
token_discovery_dirty_lookup_keys but must not restore missing cursor evidence
to zero (src/parallax/domains/asset_market/repositories/discovery_repository.py:252,
src/parallax/domains/asset_market/repositories/discovery_repository.py:300).
The target contract is that changed-row counts return
_cursor_rowcount(cursor) and fail as
discovery_repository_rowcount_required /
discovery_repository_rowcount_invalid before reporting changed lookup work
(src/parallax/domains/asset_market/repositories/discovery_repository.py:126,
src/parallax/domains/asset_market/repositories/discovery_repository.py:262,
src/parallax/domains/asset_market/repositories/discovery_repository.py:315,
src/parallax/domains/asset_market/repositories/discovery_repository.py:729,
src/parallax/domains/asset_market/repositories/discovery_repository.py:731,
tests/unit/test_discovery_repository.py:498,
tests/unit/test_discovery_repository.py:504,
tests/unit/test_discovery_repository.py:532,
tests/unit/test_discovery_repository.py:539,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2569,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2576,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2585,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2586,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2587).

Follow-up review found a separate terminal RETURNING rowcount evidence gap in
Discovery lookup-claim terminalization: terminalize_lookup_claims deletes
claimed token_discovery_dirty_lookup_keys rows before terminal ledger evidence
is emitted (src/parallax/domains/asset_market/repositories/discovery_repository.py:319,
src/parallax/domains/asset_market/repositories/discovery_repository.py:373).
The target contract is that _delete_lookup_claims_returning captures the
DELETE cursor, fetches returned rows, validates
_returned_rowcount(cursor, rows), and returns PostgreSQL-proven
deleted_count rather than list-length accounting
(src/parallax/domains/asset_market/repositories/discovery_repository.py:360,
src/parallax/domains/asset_market/repositories/discovery_repository.py:361,
src/parallax/domains/asset_market/repositories/discovery_repository.py:384,
src/parallax/domains/asset_market/repositories/discovery_repository.py:385,
src/parallax/domains/asset_market/repositories/discovery_repository.py:386,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2591,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2598,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2615,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2616,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2619).
Unit and architecture guards prove missing rowcount fails as
discovery_repository_rowcount_required, invalid or mismatched rowcount fails
as discovery_repository_rowcount_invalid, no worker_queue_terminal_events
insert happens before validation, and list-length accounting cannot return
terminal counts
(tests/unit/test_discovery_repository.py:295,
tests/unit/test_discovery_repository.py:299,
tests/unit/test_discovery_repository.py:308,
tests/unit/test_discovery_repository.py:311,
tests/unit/test_discovery_repository.py:318,
tests/unit/test_discovery_repository.py:327,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2604,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2605,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2606,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2609,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2610,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2613).

Follow-up review found the remaining Discovery state-machine evidence gap in
claim/result writes. claim_due_lookup_keys leases
token_discovery_dirty_lookup_keys with
UPDATE token_discovery_dirty_lookup_keys / RETURNING rows and validates
_returned_rowcount(cursor, rows) before returning claimed work
(src/parallax/domains/asset_market/repositories/discovery_repository.py:130,
src/parallax/domains/asset_market/repositories/discovery_repository.py:201,
src/parallax/domains/asset_market/repositories/discovery_repository.py:213,
src/parallax/domains/asset_market/repositories/discovery_repository.py:223,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2623,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2637,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2639).
The lookup result start_lookup and fail_lookup paths use RETURNING * plus
_required_returning_row(cursor, row), while finish_lookup requires
_required_single_rowcount(cursor) before reporting changed result state
(src/parallax/domains/asset_market/repositories/discovery_repository.py:388,
src/parallax/domains/asset_market/repositories/discovery_repository.py:412,
src/parallax/domains/asset_market/repositories/discovery_repository.py:425,
src/parallax/domains/asset_market/repositories/discovery_repository.py:429,
src/parallax/domains/asset_market/repositories/discovery_repository.py:484,
src/parallax/domains/asset_market/repositories/discovery_repository.py:489,
src/parallax/domains/asset_market/repositories/discovery_repository.py:517,
src/parallax/domains/asset_market/repositories/discovery_repository.py:531,
src/parallax/domains/asset_market/repositories/discovery_repository.py:744,
src/parallax/domains/asset_market/repositories/discovery_repository.py:751).
The target contract is that due-claim rowcount must match returned claim rows,
start/fail result writes must be rowcount=1 with a returned row, and finish
writes must be rowcount=1 before running/found/error state is reported. Tests
and architecture guards cover missing/invalid/mismatched rowcount, valid
rowcount=0/no-row claim no-op, rowcount=1/no-row failures, and removal of
result readback fallback from lookup result writes
(tests/unit/test_discovery_repository.py:330,
tests/unit/test_discovery_repository.py:344,
tests/unit/test_discovery_repository.py:359,
tests/unit/test_discovery_repository.py:401,
tests/unit/test_discovery_repository.py:411,
tests/unit/test_discovery_repository.py:426,
tests/unit/test_discovery_repository.py:440,
tests/unit/test_discovery_repository.py:457,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2680,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2682,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2683,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2684,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2687,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2688,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2689,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2715,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2721,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2722,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2723).

Follow-up review found the same rowcount evidence gap in enriched_events
event-anchor lifecycle accounting: attach_backfill_capture and
mark_backfill_terminal classify attach/terminal state from PostgreSQL
UPDATE results, but that classification must not restore missing cursor
evidence to a no-op. The target contract is that both lifecycle paths use
_single_row_mutation_applied(cursor) and fail as
enriched_event_repository_rowcount_required /
enriched_event_repository_rowcount_invalid unless the driver provides exactly
one of the valid single-row counts, 0 or 1
(src/parallax/domains/asset_market/repositories/enriched_event_repository.py:98,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:101,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:124,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:126,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:146,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:175,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:179,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:181,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:182,
src/parallax/domains/asset_market/repositories/enriched_event_repository.py:183,
tests/unit/test_enriched_event_repository.py:90,
tests/unit/test_enriched_event_repository.py:100,
tests/unit/test_enriched_event_repository.py:108,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2027,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2037,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2042,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2043,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2044,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2045,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:2046).

Follow-up review found the same optional connection-transaction root in
NewsProjectionDirtyTargetRepository.terminalize_targets(...): it deleted
claimed news_projection_dirty_targets, wrote worker_queue_terminal_events,
fell back to nullcontext() when the connection transaction contract was
absent, and retained a manual self.conn.commit() branch
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:531). The target
contract is that News projection dirty-target terminalization raises
RuntimeError("news_projection_dirty_target_transaction_required") before
delete or ledger SQL when the connection transaction contract is missing, and
otherwise keeps delete-returning plus terminal-ledger insert inside
with _transaction(self.conn):
(src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:383,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:398,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:402,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:580,
tests/architecture/test_news_intel_kiss_simplification.py:326,
tests/architecture/test_news_intel_kiss_simplification.py:349,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:104,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:108,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:109).

Follow-up review found the same optional connection-transaction root in ops projection dirty repair: enqueue_projection_dirty_targets execute mode scanned news_items / news_sources, wrote news_projection_dirty_targets, and previously allowed a missing connection transaction contract to continue through nullcontext() (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:546). The target contract is that dry-run keeps the explicit read-only nullcontext() branch, while execute mode calls _transaction(repos.conn) and raises RuntimeError("projection_dirty_targets_transaction_required") before repair scans or dirty enqueue when the connection transaction contract is missing (src/parallax/app/runtime/projection_dirty_targets.py:22, src/parallax/app/runtime/projection_dirty_targets.py:49, src/parallax/app/runtime/projection_dirty_targets.py:184, src/parallax/app/runtime/projection_dirty_targets.py:188, tests/unit/test_ops_projection_dirty_targets.py:91, tests/unit/test_ops_projection_dirty_targets.py:103, tests/architecture/test_news_intel_kiss_simplification.py:996, tests/architecture/test_news_intel_kiss_simplification.py:1006, tests/architecture/test_news_intel_kiss_simplification.py:1008).

Follow-up SQL-performance review found that ops projection dirty repair must stay a keyset enqueue path rather than a wide News projection input rebuild. _enqueue_news_targets now calls _fetch_news_item_rows only when news_item_projections are selected, and source-quality-only repair proves no FROM news_items scan. _fetch_news_item_rows selects only items.news_item_id, items.published_at_ms AS source_watermark_ms, and items.agent_admission_status; architecture guards reject LEFT JOIN LATERAL, news_token_mentions, news_fact_candidates, agent_admission_json, and provider signal/impact wide rows from the repair query (src/parallax/app/runtime/projection_dirty_targets.py:62, src/parallax/app/runtime/projection_dirty_targets.py:77, src/parallax/app/runtime/projection_dirty_targets.py:163, src/parallax/app/runtime/projection_dirty_targets.py:171, src/parallax/app/runtime/projection_dirty_targets.py:173, src/parallax/app/runtime/projection_dirty_targets.py:175, tests/unit/test_ops_projection_dirty_targets.py:199, tests/unit/test_ops_projection_dirty_targets.py:235, tests/architecture/test_news_intel_kiss_simplification.py:1012, tests/architecture/test_news_intel_kiss_simplification.py:1018, tests/architecture/test_news_intel_kiss_simplification.py:1019, tests/architecture/test_news_intel_kiss_simplification.py:1020, tests/architecture/test_news_intel_kiss_simplification.py:1022, tests/architecture/test_news_intel_kiss_simplification.py:1023, tests/architecture/test_news_intel_kiss_simplification.py:1024, tests/architecture/test_news_intel_kiss_simplification.py:1027, tests/architecture/test_news_intel_kiss_simplification.py:1028, tests/architecture/test_news_intel_kiss_simplification.py:1029, tests/architecture/test_news_intel_kiss_simplification.py:1030, tests/architecture/test_news_intel_kiss_simplification.py:1031).

Follow-up review found the same optional connection-transaction root in PulseJobsRepository: terminal/dead paths updated pulse_agent_jobs, wrote worker_queue_terminal_events, fell back to nullcontext() when connection transaction support was absent, and retained manual commit branches (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:561, src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:594). The target contract is that Pulse job terminal/dead transitions fail before job-state or terminal-ledger SQL when connection transaction support is missing, and otherwise keep both writes inside the connection transaction (src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:596, src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:197, tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:55, tests/architecture/test_pulse_no_compat.py:255).

Follow-up review found the same optional connection-transaction root in PulseAdmissionRepository.claim_pulse_admission(...): admission wrote pulse_candidate_edge_state, used SELECT ... FOR UPDATE, depended on _pulse_repository_shared._transaction(conn), and fell back to nullcontext() when transaction support was missing (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:576, docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:578). The target contract is that Pulse admission raises RuntimeError("pulse_repository_transaction_required") before edge or budget SQL when conn.transaction is missing or not callable, while keeping admission writes inside with _transaction(self.conn): (src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py:122, src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py:124, src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py:126, src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py:213, tests/unit/domains/pulse_lab/test_pulse_admission_repository.py:116, tests/architecture/test_pulse_no_compat.py:873).

Follow-up review found the same optional connection-transaction root in Macro observation-series refresh: MacroIntelRepository.refresh_observation_series_rows_for_concepts(...) used _transaction_context around macro_observation_series_rows and macro_observation_series_publication_state, and previously fell back to nullcontext() when connection transaction support was missing (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:591). The target contract is that changed current-row delete/insert and publication-state update run inside the connection transaction and fail before SQL when that contract is missing (src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1345, src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1351, src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1352, src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2262, src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2263, tests/architecture/test_macro_no_compatibility_contract.py:224).

Follow-up review found the same repository-owned manual commit root in Macro
projection dirty-target control-plane mutations: claim_macro_projection_dirty_targets(...),
mark_macro_projection_dirty_targets_done(...), and
mark_macro_projection_dirty_targets_error(...) still executed
macro_projection_dirty_targets SQL and then called self.conn.commit() when
the repository owned the commit (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:2244,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:2245,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:2251). The target contract is that repository-owned
Macro dirty-target claim/done/error mutations require a callable connection
transaction before SQL, while MacroViewProjectionWorker keeps those writes
caller-owned with commit=False inside RepositorySession.transaction
(src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1037,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1064,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1097,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1150,
src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:54,
src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py:62,
docs/WORKERS.md:349).

Follow-up review found the same optional repository-contract root in Token Radar
downstream dirty-target fan-out after rank-set changes. The target contract is
direct repository-session access to self.repos.pulse_trigger_dirty_targets,
self.repos.narrative_admission_dirty_targets,
self.repos.token_profile_current_dirty_targets, and
self.repos.token_capture_tier_dirty_targets, so missing downstream repositories
are session wiring failures instead of optional work
(src/parallax/domains/token_intel/services/token_radar_projection.py:920,
src/parallax/domains/token_intel/services/token_radar_projection.py:967,
src/parallax/domains/token_intel/services/token_radar_projection.py:1012,
src/parallax/domains/token_intel/services/token_radar_projection.py:1037).
Architecture tests reject the old optional repository probes and if repo is None:
branches
(tests/architecture/test_token_radar_source_width_contract.py:130,
tests/architecture/test_token_radar_source_width_contract.py:154,
tests/architecture/test_token_radar_source_width_contract.py:155,
tests/architecture/test_token_radar_source_width_contract.py:156,
tests/architecture/test_token_radar_source_width_contract.py:157,
tests/architecture/test_token_radar_source_width_contract.py:158,
tests/architecture/test_token_radar_source_width_contract.py:161,
tests/architecture/test_token_radar_source_width_contract.py:162,
tests/architecture/test_token_radar_source_width_contract.py:163,
tests/architecture/test_token_radar_source_width_contract.py:164).

Follow-up review found the same manual-commit root in Pulse job/run mutations: enqueue_job(...), mark_job_succeeded(...), running-job release, and mark_stale_agent_runs_failed(...) still used self.conn.commit() or getattr(self.conn, "transaction", None) compatibility under default commit=True (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:606). The target contract is that repository-owned commits use _run_job_write to enter the connection transaction before job/run SQL, while commit false remains reserved for an outer session transaction (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:614, src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:138, src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:252, src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:608, tests/architecture/test_pulse_no_compat.py:263).

Follow-up review found the same manual-commit root across the remaining Pulse
agent write repositories: run, eval, evidence, candidate, playbook, and ordinary
admission mutations still accepted repository-owned commits under the old manual
commit semantics (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:621,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:623). The target
contract is that repository-owned commits in this agent write chain enter the
shared Pulse connection transaction before run, step, eval, packet, candidate,
playbook, edge, or budget SQL, while caller-owned writes remain reserved for the
outer repository-session transaction already used by the worker/service path
(src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py:130,
src/parallax/domains/pulse_lab/repositories/_pulse_repository_shared.py:132,
src/parallax/domains/pulse_lab/repositories/pulse_runs_repository.py:105,
src/parallax/domains/pulse_lab/repositories/pulse_agent_eval_repository.py:66,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:73,
src/parallax/domains/pulse_lab/repositories/pulse_candidates_repository.py:12,
src/parallax/domains/pulse_lab/repositories/pulse_playbooks_repository.py:9,
src/parallax/domains/pulse_lab/repositories/pulse_admission_repository.py:64).

Follow-up review found the same repository-owned manual commit root in the
Pulse trigger dirty target control-plane repository: enqueue, due-claim,
done, error, and reschedule mutations still used direct connection commit
semantics when the repository owned the commit
(src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:154,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:204,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:252,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:313,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:371).
The target contract is that repository-owned Pulse trigger dirty-target queue
mutations enter the same shared Pulse connection transaction before SQL; empty
inputs may return without SQL, and caller-owned writes remain reserved for the
outer repository-session transaction.

Follow-up review found the same repository-owned manual commit root in the
News projection dirty-target repository's ordinary queue mutations: enqueue,
due-claim, done, and error paths still executed news_projection_dirty_targets
SQL before direct connection commit when the repository owned the commit
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:655,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:657).
The target contract is that repository-owned News dirty-target queue mutations
enter the connection transaction before SQL; empty inputs may return without
SQL, and caller-owned writes remain reserved for the outer repository-session
transaction
(src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:163,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:226,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:273,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:389,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:596,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:603).

Follow-up review found the same rowcount evidence gap in News projection
dirty-target completion accounting: architecture coverage rejects
getattr(cursor, "rowcount", 0) and
int(getattr(cursor, "rowcount", 0) or 0), and the target contract requires
_cursor_rowcount(cursor) to read PostgreSQL cursor.rowcount plus typed
news_projection_dirty_target_rowcount_required /
news_projection_dirty_target_rowcount_invalid failures before done/error
changed-row counts are returned
(tests/architecture/test_news_intel_kiss_simplification.py:400,
tests/architecture/test_news_intel_kiss_simplification.py:401,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:274,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:387,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:613,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:615,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:617,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:619,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:626).

Follow-up review found the same rowcount evidence gap in the ordinary
NewsRepository write-count paths: item lifecycle, source-quality status, and
page-row mutation methods still had default zero-row accounting through
getattr(cursor, "rowcount", 0), int(getattr(cursor, "rowcount", 0) or 0),
or cursor.rowcount or 0. The target contract is that these changed-row counts
use _cursor_rowcount(cursor) and fail as
news_repository_rowcount_required / news_repository_rowcount_invalid before
reporting zero changed News work
(tests/architecture/test_news_intel_kiss_simplification.py:498,
tests/architecture/test_news_intel_kiss_simplification.py:499,
tests/architecture/test_news_intel_kiss_simplification.py:500,
tests/architecture/test_news_intel_kiss_simplification.py:501,
tests/architecture/test_news_intel_kiss_simplification.py:503,
tests/architecture/test_news_intel_kiss_simplification.py:510,
tests/architecture/test_news_intel_kiss_simplification.py:511,
tests/architecture/test_news_intel_kiss_simplification.py:512,
tests/architecture/test_news_intel_kiss_simplification.py:513,
tests/architecture/test_news_intel_kiss_simplification.py:514,
tests/architecture/test_news_intel_kiss_simplification.py:516,
src/parallax/domains/news_intel/repositories/news_repository.py:209,
src/parallax/domains/news_intel/repositories/news_repository.py:2573,
src/parallax/domains/news_intel/repositories/news_repository.py:5031,
src/parallax/domains/news_intel/repositories/news_repository.py:5034,
src/parallax/domains/news_intel/repositories/news_repository.py:5038,
src/parallax/domains/news_intel/repositories/news_repository.py:5040,
src/parallax/domains/news_intel/repositories/news_repository.py:5062,
src/parallax/domains/news_intel/repositories/news_repository.py:5064).

Follow-up review found a narrower NewsRepository source-disable gap on top of
that ordinary rowcount contract: disable_unconfigured_sources
disabled stale configured sources through UPDATE news_sources / RETURNING *
and returned disabled-source accounting from return len(rows). The target
contract is that source-disable RETURNING rows are validated through
_returned_rowcount(cursor, rows), the helper first reads
_cursor_rowcount(cursor), missing rowcount fails as
news_repository_rowcount_required, invalid or mismatched rowcount fails as
news_repository_rowcount_invalid, reconcile callers may still receive verified
disabled rows, and disable-count callers receive only the PostgreSQL-proven count
(src/parallax/domains/news_intel/repositories/news_repository.py:209,
src/parallax/domains/news_intel/repositories/news_repository.py:364,
src/parallax/domains/news_intel/repositories/news_repository.py:370,
src/parallax/domains/news_intel/repositories/news_repository.py:375,
src/parallax/domains/news_intel/repositories/news_repository.py:395,
src/parallax/domains/news_intel/repositories/news_repository.py:408,
src/parallax/domains/news_intel/repositories/news_repository.py:5046,
src/parallax/domains/news_intel/repositories/news_repository.py:5058,
src/parallax/domains/news_intel/repositories/news_repository.py:5062,
src/parallax/domains/news_intel/repositories/news_repository.py:5064,
src/parallax/domains/news_intel/repositories/news_repository.py:5065,
src/parallax/domains/news_intel/repositories/news_repository.py:5067,
src/parallax/domains/news_intel/repositories/news_repository.py:5068,
src/parallax/domains/news_intel/repositories/news_repository.py:5070,
src/parallax/domains/news_intel/repositories/news_repository.py:5075,
src/parallax/domains/news_intel/repositories/news_repository.py:5078,
src/parallax/domains/news_intel/repositories/news_repository.py:5080,
tests/unit/domains/news_intel/test_news_repository_queries.py:583,
tests/unit/domains/news_intel/test_news_repository_queries.py:590,
tests/unit/domains/news_intel/test_news_repository_queries.py:599,
tests/unit/domains/news_intel/test_news_repository_queries.py:608,
tests/architecture/test_news_intel_kiss_simplification.py:517,
tests/architecture/test_news_intel_kiss_simplification.py:525,
tests/architecture/test_news_intel_kiss_simplification.py:527,
tests/architecture/test_news_intel_kiss_simplification.py:530,
tests/architecture/test_news_intel_kiss_simplification.py:531,
tests/architecture/test_news_intel_kiss_simplification.py:532,
tests/architecture/test_news_intel_kiss_simplification.py:533,
tests/architecture/test_news_intel_kiss_simplification.py:536,
tests/architecture/test_news_intel_kiss_simplification.py:541).

Follow-up review found the same completion-token attempt fallback inside News
projection dirty-target completion keys. The old _key_records(...) path used
int(key.get("attempt_count") or 0), so a malformed page/source-quality dirty
claim completion token missing attempt_count became a zero-attempt key instead
of failing before SQL (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6173,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6175,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6178). The target contract is
that mark_done(...), mark_error(...), delete_claimed_targets(...), and
terminalize_targets(...) require the claimed row attempt_count in their
completion keys and fail before transaction entry or SQL when that contract is
missing (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6174,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:278,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:383,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:561,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:580,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:582,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:584,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:586,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:186,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:194,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:197,
tests/architecture/test_news_intel_kiss_simplification.py:377,
tests/architecture/test_news_intel_kiss_simplification.py:388,
tests/architecture/test_news_intel_kiss_simplification.py:389,
tests/architecture/test_news_intel_kiss_simplification.py:390).

Follow-up review found the same repository-owned manual commit root in the
Token Radar source dirty event repository: enqueue, due-claim, done, and error
paths still executed token_radar_source_dirty_events SQL before direct
connection commit when the repository owned the commit
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:685,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:687).
The target contract is that repository-owned Token Radar source dirty queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:704,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:706).

Follow-up review found the same repository-owned manual commit root in the
Token Radar target dirty queue repository: target enqueue, market enqueue,
due-claim, recent-resolved catch-up enqueue, market-current enqueue, done, and
error paths still executed token_radar_dirty_targets SQL before direct
connection commit when the repository owned the commit
(src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:57,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:117,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:275,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:381).
The target contract is that repository-owned Token Radar target dirty queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction.

Follow-up review found the same completion-token attempt fallback inside Token
Radar target/source dirty repositories after the service-level claim hard cut.
TokenRadarDirtyTargetRepository._key_records(...) and
TokenRadarSourceDirtyEventRepository._key_records(...) still restored missing
completion-token attempts through int(key.get("attempt_count") or 0) before
raising an invalid-attempt error (docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6209,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6210,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6211,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6213). The target contract is
that both repositories read key["attempt_count"], require a positive claimed
attempt for done/error completion keys, and fail before SQL without
synthesizing zero attempts (src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:823,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:862,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:866,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:320,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:376,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:367,
tests/unit/test_token_radar_dirty_target_repository.py:237,
tests/unit/test_token_radar_dirty_target_repository.py:247,
tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py:137,
tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py:148,
tests/architecture/test_token_radar_source_width_contract.py:177,
tests/architecture/test_token_radar_source_width_contract.py:185,
tests/architecture/test_token_radar_source_width_contract.py:191).

Follow-up review found the same repository-owned manual commit root one market
stage earlier in MarketTickCurrentDirtyTargetRepository: market-current
dirty enqueue, due-claim, done, and error paths still executed
market_tick_current_dirty_targets SQL before direct connection commit when
the repository owned the commit
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:740,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:744,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:746).
The target contract is that repository-owned Market Tick Current dirty queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:766,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:768).

Follow-up review found the same completion-token attempt fallback in
MarketTickCurrentDirtyTargetRepository._claim_records(...): completion claims
for mark_done(...) and mark_error(...) restored missing attempts through
int(claim.get("attempt_count") or 0) before raising an invalid-attempt error
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6243,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6245,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6247). The target contract is
that market-current dirty done/error completion keys read
claim["attempt_count"], require a positive claimed-row attempt, and fail
before SQL without synthesizing zero attempts
(src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:305,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:324,
src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:326,
tests/unit/test_market_tick_current_repository.py:185,
tests/unit/test_market_tick_current_repository.py:198,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:983,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:986,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:991).

Follow-up review found the same dirty-completion attempt fallback in the Asset
Market profile/icon refresh control plane: Token Profile Current, Token Image
Source, and Asset Profile Refresh dirty completion helpers restored missing
claim attempts through int(claim.get("attempt_count") or 0) before failing
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6277,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6279,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6287,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6292).
The target contract is that token_profile_current_dirty_targets,
token_image_source_dirty_targets, and asset_profile_refresh_targets
completion keys read claim["attempt_count"], require a positive claimed-row
attempt, and fail before SQL without synthesizing zero attempts
(src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:52,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:67,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:57,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:386,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:401,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:403,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:506,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:541,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:543,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:401,
tests/unit/domains/asset_market/test_token_profile_current_dirty_targets.py:239,
tests/unit/domains/asset_market/test_token_image_source_dirty_targets.py:92,
tests/unit/domains/asset_market/test_asset_profile_refresh_targets.py:77,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1586,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1602,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1604).

Follow-up review found the same dirty-completion attempt fallback in Discovery,
Narrative Admission, and Pulse Trigger control queues: malformed completion
tokens missing attempt_count were either restored to zero or filtered into a
silent no-op before SQL
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6321,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6326,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6335,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6343).
The target contract is that token_discovery_dirty_lookup_keys,
narrative_admission_dirty_targets, and pulse_trigger_dirty_targets
completion keys read claim["attempt_count"], require a positive claimed-row
attempt, and fail before SQL without synthesizing zero attempts
(src/parallax/domains/asset_market/repositories/discovery_repository.py:62,
src/parallax/domains/asset_market/repositories/discovery_repository.py:707,
src/parallax/domains/asset_market/repositories/discovery_repository.py:724,
src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py:507,
src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py:606,
src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py:637,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:57,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:462,
src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py:487,
tests/unit/test_discovery_repository.py:259,
tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py:322,
tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py:252,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1185,
tests/architecture/test_pulse_no_compat.py:418).

Follow-up review found the same attempt fallback one layer above repository
completion in Event Anchor Backfill and Resolution Refresh worker retry
decisions: worker code treated missing claimed-row attempt_count as zero
before choosing reschedule, terminal, or retry-budget branches
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6367,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6369,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6371,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:6380).
The target contract is that claimed event_anchor_backfill_jobs and
token_discovery_dirty_lookup_keys rows expose a positive attempt_count
before retry/terminal guards run; worker code must read row["attempt_count"]
or claim["attempt_count"] directly and fail malformed claim state before
branching
(src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:273,
src/parallax/domains/asset_market/ARCHITECTURE.md:21,
src/parallax/domains/asset_market/runtime/event_anchor_backfill_worker.py:472,
src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py:489,
src/parallax/domains/asset_market/ARCHITECTURE.md:30,
src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py:491,
tests/unit/test_event_anchor_backfill_worker.py:288,
tests/unit/test_event_anchor_backfill_worker.py:298,
tests/unit/test_resolution_refresh_worker.py:180,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1206,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1224,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1225).

Follow-up review found the same fallback in Pulse agent job execution/audit and
Macro Sync retry-budget classification: Pulse code built run ids, trace metadata,
failure state, timeout cancellation, backpressure release, and provider cooldown
CAS from missing job attempts as zero, while Macro Sync treated a missing sync
window attempt as zero and missing max attempts as one. The target contract is
that claimed pulse agent job attempt_count, Pulse max_attempts, and claimed
macro_sync_windows attempt_count / max_attempts are required before those
state-machine decisions; malformed control rows fail before repository SQL,
agent audit construction, or retry/final failure classification
(src/parallax/domains/pulse_lab/ARCHITECTURE.md:45,
src/parallax/domains/pulse_lab/ARCHITECTURE.md:57,
src/parallax/domains/pulse_lab/ARCHITECTURE.md:58,
src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py:129,
src/parallax/domains/pulse_lab/services/pulse_candidate_job_service.py:659,
src/parallax/domains/pulse_lab/services/pulse_decision_runtime.py:135,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:269,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:270,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:334,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:398,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:439,
src/parallax/domains/macro_intel/ARCHITECTURE.md:16,
src/parallax/domains/macro_intel/services/macro_sync_service.py:463,
src/parallax/domains/macro_intel/services/macro_sync_service.py:468,
src/parallax/domains/macro_intel/services/macro_sync_service.py:478,
tests/unit/domains/pulse_lab/test_pulse_candidate_job_service.py:81,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:163,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:176,
tests/unit/test_pulse_decision_agent_client.py:303,
tests/unit/domains/macro_intel/test_macro_sync_service.py:361,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1232).

Follow-up review found the same repository-owned manual commit root in the
Token Profile Current dirty queue repository: profile-current dirty enqueue,
due-claim, done, and error paths executed token_profile_current_dirty_targets
SQL before direct connection commit when the repository owned the commit
(src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:14,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:52,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:165,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:228,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:280,
src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py:432).
The target contract is that repository-owned Token Profile Current dirty queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction.

Follow-up review found the same repository-owned manual commit root in the
Token Image Source dirty queue repository: image-source dirty enqueue,
due-claim, done, and error paths executed token_image_source_dirty_targets
SQL before direct connection commit when the repository owned the commit
(src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:68,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:162,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:291,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:346,
src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py:400).
The target contract is that repository-owned Token Image Source dirty queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction.

Follow-up review found the same repository-owned manual commit root in the
Asset Profile Refresh target repository: provider refresh target enqueue,
due-claim, reschedule, and error paths executed asset_profile_refresh_targets
SQL before direct connection commit when the repository owned the commit
(src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:15,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:57,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:127,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:129,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:144,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:178,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:180,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:226,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:228,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:279,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:295,
src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py:305).
The target contract is that repository-owned Asset Profile Refresh target queue
mutations enter the connection transaction before SQL; empty inputs may return
without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction.

Follow-up review found the same repository-owned manual commit root in the
Asset Profile source-cache repository: ready-profile upserts and missing/error
status upserts executed asset_profiles SQL before direct connection commit
when the repository owned the commit
(src/parallax/domains/asset_market/repositories/asset_profile_repository.py:48,
src/parallax/domains/asset_market/repositories/asset_profile_repository.py:120).
The target contract is that repository-owned Asset Profile source-cache
mutations enter the connection transaction before SQL, while
asset_profile_refresh worker service writes remain caller-owned inside the
outer repository-session transaction
(src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py:14,
src/parallax/domains/asset_market/services/asset_profile_refresh.py:48,
src/parallax/domains/asset_market/services/asset_profile_refresh.py:65).

Follow-up review found the same repository-owned manual commit root in the CEX
profile source-cache repository: upsert_ready_profile_if_token_exists
executes cex_token_profiles SQL and must enter the connection transaction
before that write when the repository owns the commit
(src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:38,
src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:56,
src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:75,
src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:93).
Root63 made sync_cex_token_profiles hold a callable connection transaction,
call upsert_ready_profile_if_token_exists, and pass commit=False; the
service now also materializes provider rows through _formal_profile(profile)
before the transaction, while the repository requires
_required_raw_payload(raw_payload) instead of an empty raw-payload default
(src/parallax/domains/asset_market/services/cex_token_profile_sync.py:12,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:13,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:20,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:27,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:36,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:52,
src/parallax/domains/asset_market/services/cex_token_profile_sync.py:86,
src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:83,
src/parallax/domains/asset_market/repositories/cex_token_profile_repository.py:124).

Follow-up review found the same repository-owned manual commit root in the
Token Capture Tier dirty repository: rank-set dirty enqueue, due-claim, and
done paths executed token_capture_tier_dirty_targets SQL before direct
connection commit when the repository owned the commit
(src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:15,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:37,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:50,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:106,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:107,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:122,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:149,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:151,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:169,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:196,
src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py:206).
The target contract is that repository-owned Token Capture Tier dirty queue
mutations enter the connection transaction before SQL; empty done inputs may
return without SQL, and caller-owned writes remain reserved for the outer
repository-session transaction.

Follow-up review found an optional connection-transaction probe in Token Radar
rank publication: refresh_rank_set(...) wrapped stale-running cleanup, offset
advance, current-row publication, and run finish in _transaction_context, while
the helper still used getattr(conn, "transaction", None) and produced a
non-contract TypeError for non-callable transaction attributes
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:888,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:891,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:892,
src/parallax/domains/token_intel/services/token_radar_projection.py:580,
src/parallax/domains/token_intel/services/token_radar_projection.py:611,
src/parallax/domains/token_intel/services/token_radar_projection.py:1977,
tests/architecture/test_token_radar_publication_state_hard_cut.py:302).
The target contract is that Token Radar rank publication requires a callable
connection transaction before current-row/publication-state SQL and fails with
the projection contract error when that connection contract is absent or
malformed (src/parallax/domains/token_intel/services/token_radar_projection.py:611,
src/parallax/domains/token_intel/services/token_radar_projection.py:1977,
src/parallax/domains/token_intel/services/token_radar_projection.py:1979,
src/parallax/domains/token_intel/services/token_radar_projection.py:1981,
src/parallax/domains/token_intel/services/token_radar_projection.py:1983).

Follow-up hardening found the same optional probe shape in Event Anchor
repository terminal writes: Root39 had already required
expire_stale(...) and mark_terminal(...) to use _transaction(self._conn),
but the transaction helper still used getattr(conn, "transaction", None)
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:910,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:911,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:914).
The target contract is that expire_stale(...), mark_terminal(...), and
_transaction(conn) protect Event Anchor job terminal update and
worker_queue_terminal_events ledger writes with direct callable connection
transaction support; missing or malformed support raises
event_anchor_repository_transaction_required before terminal
SQL (src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:111,
src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:192,
src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:564,
src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:568,
src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:570,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:923,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:918,
tests/unit/test_event_anchor_backfill_job_repository.py:151).

Follow-up review found another public-query boundary duplicate in ops
diagnostics: /api/ops/diagnostics already owned the public since_hours,
window, and scope defaults and validated window / scope before calling
runtime composition, but ops_diagnostics_payload(...) still carried the same
defaults inside runtime composition
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9007,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9011,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9012,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9013).
The target contract is that route signatures own product defaults, shared
validators fail malformed values, and runtime diagnostics payload construction
receives explicit query boundaries so direct callers cannot synthesize 1h /
all diagnostic reads outside the public surface
(src/parallax/app/surfaces/api/routes_ops.py:28,
src/parallax/app/surfaces/api/routes_ops.py:29,
src/parallax/app/surfaces/api/routes_ops.py:30,
src/parallax/app/surfaces/api/routes_ops.py:36,
src/parallax/app/surfaces/api/routes_ops.py:37,
src/parallax/app/surfaces/api/routes_ops.py:38,
src/parallax/app/runtime/ops_diagnostics.py:85,
src/parallax/app/runtime/ops_diagnostics.py:86,
src/parallax/app/runtime/ops_diagnostics.py:87,
tests/unit/test_ops_diagnostics.py:49,
tests/architecture/test_api_read_paths_provider_free.py:87).

Follow-up review found the same query-window duplication in Pulse freshness
health: public Signal Pulse health and CLI health/replay callers already pass a
4h or operator-specified health horizon explicitly, but the lower health
repository/service still retained their own since_hours=4 defaults
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9041,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9045,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9046,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9048,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9049).
The target contract is that Pulse freshness SQL receives explicit
since_hours from its caller, so direct repository/service callers cannot
synthesize a 4h health read outside the public read model or CLI surface
(src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py:166,
src/parallax/domains/pulse_lab/read_models/signal_pulse_service.py:170,
src/parallax/app/surfaces/cli/commands/pulse_replay.py:23,
src/parallax/app/surfaces/cli/commands/pulse_replay.py:27,
src/parallax/domains/pulse_lab/repositories/pulse_read_repository.py:306,
src/parallax/domains/pulse_lab/services/pulse_freshness_health.py:30,
tests/unit/domains/pulse_lab/test_pulse_read_repository_health.py:33,
tests/unit/domains/pulse_lab/test_write_gate_health.py:68,
tests/architecture/test_pulse_no_compat.py:802).

Follow-up review found a non-SQL compatibility fallback in Pulse recommendation
clipping: FinalDecision.playbook.monitoring_horizon is a required v2 decision
field, but the clipper still replaced missing horizons with 1h while creating
ignore or abstain playbook shapes
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9077,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9081,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9082,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9084,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9085).
The target contract is that recommendation clipping consumes formal decision
output, preserves the validated playbook horizon, and fails malformed decision
payloads before replay/audit can present a locally synthesized horizon as model
output (src/parallax/domains/pulse_lab/services/recommendation_clipper.py:86,
src/parallax/domains/pulse_lab/services/recommendation_clipper.py:112,
src/parallax/domains/pulse_lab/services/recommendation_clipper.py:127,
src/parallax/domains/pulse_lab/services/recommendation_clipper.py:148,
src/parallax/domains/pulse_lab/services/recommendation_clipper.py:151,
src/parallax/domains/pulse_lab/ARCHITECTURE.md:280,
tests/unit/test_pulse_recommendation_clipper.py:64,
tests/architecture/test_pulse_no_compat.py:816).

Follow-up review found the same public-query boundary duplication in Macro
asset correlation: the API route already owns and validates the public 60d
window default before loading observations, but the correlation builder still
kept its own window="60d" default
(docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9115,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9119,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9120,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9121,
docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md:9123).
The target contract is that /api/macro/assets/correlation resolves the
requested correlation window, computes PostgreSQL query bounds from that
validated value, and passes the same window explicitly into the pure builder
(src/parallax/app/surfaces/api/routes_macro.py:69,
src/parallax/app/surfaces/api/routes_macro.py:73,
src/parallax/app/surfaces/api/routes_macro.py:189,
src/parallax/app/surfaces/api/routes_macro.py:190,
src/parallax/domains/macro_intel/services/macro_asset_correlation.py:52,
tests/unit/domains/macro_intel/test_macro_asset_correlation.py:13,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1787).

Follow-up review found the same write-count evidence gap in Macro Intel:
complete_macro_sync_window, retry_macro_sync_window,
fail_macro_sync_window, update_macro_sync_state,
rebuild_macro_sync_state, enqueue_macro_projection_dirty_target,
enqueue_macro_projection_dirty_targets_for_changes,
mark_macro_projection_dirty_targets_done,
mark_macro_projection_dirty_targets_error,
_delete_exited_observation_series_rows, and
_insert_observation_series_rows_chunk all return write-count or state
classification results for Macro sync/projection/current-row mutations
(src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:561,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:596,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:638,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:738,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:767,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:822,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:905,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1097,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1150,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1479,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1533).
The target contract is that `_cursor_rowcount` and `_single_rowcount` require
real PostgreSQL `cursor.rowcount` evidence, while tests cover missing/invalid
rowcount and guard against default or length-based compatibility accounting
(src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2219,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2251,
src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:2253,
tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py:480,
tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py:503,
tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py:521,
tests/unit/domains/macro_intel/test_macro_generation_swap.py:265,
tests/unit/domains/macro_intel/test_macro_generation_swap.py:281,
tests/architecture/test_macro_no_compatibility_contract.py:249).

Follow-up review found the same rowcount evidence gap in Narrative admission
serving-row accounting. upsert_admissions writes narrative_admissions and
returns upserted, while stale_admission_target deletes
narrative_admissions and returns staled_admissions
(src/parallax/domains/narrative_intel/repositories/narrative_repository.py:28,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:91,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:129,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:253,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:277,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:287).
The target contract is that _cursor_rowcount reads real PostgreSQL
cursor.rowcount, failing as narrative_repository_rowcount_required or
narrative_repository_rowcount_invalid, while tests and architecture guards
cover missing/invalid rowcount plus default-zero fallback removal
(src/parallax/domains/narrative_intel/repositories/narrative_repository.py:756,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:758,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:760,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:762,
src/parallax/domains/narrative_intel/repositories/narrative_repository.py:764,
tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py:107,
tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py:110,
tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py:136,
tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py:139,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1829,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1830,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1837).

Follow-up review found the same rowcount evidence gap in Pulse stale agent-run
cleanup. mark_stale_agent_runs_failed updates pulse_agent_runs and returns
changed-run counts from _cursor_rowcount(cursor)
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:559,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:572,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:586,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:587).
The target contract is that _cursor_rowcount reads PostgreSQL
cursor.rowcount, failing as pulse_jobs_repository_rowcount_required or
pulse_jobs_repository_rowcount_invalid, while tests and architecture guards
cover missing/invalid rowcount plus default-zero fallback removal
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:634,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:636,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:638,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:640,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:642,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:220,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:224,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:230,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:235,
tests/architecture/test_pulse_no_compat.py:424,
tests/architecture/test_pulse_no_compat.py:434,
tests/architecture/test_pulse_no_compat.py:435,
tests/architecture/test_pulse_no_compat.py:436,
tests/architecture/test_pulse_no_compat.py:437).

Follow-up review then found the same rowcount evidence gap in Pulse job
terminal/dead batches: terminalize_exhausted_stale_running_jobs and
terminalize_stale_jobs_by_window update pulse_agent_jobs, return job rows,
validate _returned_rowcount(cursor, rows), and only then write terminal ledger
rows
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:191,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:215,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:221,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:225,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:226,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:228,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:518,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:536,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:543,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:547,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:548,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:550).
The target contract is that _returned_rowcount first reads
cursor.rowcount, requires it to match len(rows), fails missing evidence as
pulse_jobs_repository_rowcount_required, and fails invalid or mismatched
evidence as pulse_jobs_repository_rowcount_invalid
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:636,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:638,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:640,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:646,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:647,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:648,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:649,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:650,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:241,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:261,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:268,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:275,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:280,
tests/architecture/test_pulse_no_compat.py:445,
tests/architecture/test_pulse_no_compat.py:455,
tests/architecture/test_pulse_no_compat.py:456,
tests/architecture/test_pulse_no_compat.py:457,
tests/architecture/test_pulse_no_compat.py:458,
tests/architecture/test_pulse_no_compat.py:459,
tests/architecture/test_pulse_no_compat.py:460,
tests/architecture/test_pulse_no_compat.py:461).

Follow-up review found the remaining single-row Pulse job state-machine
RETURNING gap. enqueue_job writes pulse_agent_jobs through RETURNING *
and now returns through _required_returning_row(cursor, row), while claim,
success, failure, retry, timeout cancellation, and release paths update
pulse_agent_jobs and return through _optional_returning_row
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:25,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:55,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:114,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:139,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:146,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:165,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:184,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:189,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:248,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:258,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:282,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:293,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:315,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:328,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:347,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:384,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:411,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:431,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:453,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:477).
The target contract is that _single_returning_rowcount reads PostgreSQL
cursor.rowcount, accepts only rowcount 0/1, and requires returned-row presence
to match that count before job state, retry/dead classification, terminal retry,
timeout cancellation, release, or terminal ledger effects are reported; tests
and architecture guards cover missing/invalid/mismatched rowcount plus chained
.fetchone() compatibility removal
(src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:653,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:654,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:655,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:657,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:636,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:662,
src/parallax/domains/pulse_lab/repositories/pulse_jobs_repository.py:668,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:291,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:315,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:342,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:363,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:429,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:445,
tests/unit/domains/pulse_lab/test_pulse_jobs_repository.py:455,
tests/architecture/test_pulse_no_compat.py:468,
tests/architecture/test_pulse_no_compat.py:483,
tests/architecture/test_pulse_no_compat.py:484,
tests/architecture/test_pulse_no_compat.py:491,
tests/architecture/test_pulse_no_compat.py:501,
tests/architecture/test_pulse_no_compat.py:504).

Follow-up review found the same chained-mutation rowcount evidence gap in
Pulse evidence packet persistence. The packet upsert now proves
pulse_evidence_packets through RETURNING evidence_packet_id, but the
associated UPDATE pulse_agent_runs run-link must also prove it affected
exactly one audit row before upsert_packet returns
(src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:42,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:48,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:67,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:86,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:87,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:89,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:96).
The target contract is that _required_single_rowcount rejects missing,
invalid, zero-row, or multi-row run-link evidence as a repository contract
failure; tests and architecture guards cover the second mutation independently
from the packet RETURNING proof
(src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:31,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:33,
src/parallax/domains/pulse_lab/repositories/pulse_evidence_repository.py:34,
tests/unit/domains/pulse_lab/test_pulse_evidence_repository.py:101,
tests/unit/domains/pulse_lab/test_pulse_evidence_repository.py:126,
tests/architecture/test_pulse_no_compat.py:718,
tests/architecture/test_pulse_no_compat.py:721,
tests/architecture/test_pulse_no_compat.py:722).

Follow-up review found the same returned-rowcount evidence gap in
ProjectionRepository dirty-range claims. claim_dirty_ranges leases
projection_dirty_ranges through UPDATE projection_dirty_ranges with
RETURNING ranges.*, so returned rows are worker lease identities, not just
query output
(src/parallax/domains/token_intel/repositories/projection_repository.py:296,
src/parallax/domains/token_intel/repositories/projection_repository.py:305,
src/parallax/domains/token_intel/repositories/projection_repository.py:317,
src/parallax/domains/token_intel/repositories/projection_repository.py:322).
The target contract is that claim rows are fetched from a saved cursor,
_returned_rowcount(cursor, rows) validates PostgreSQL cursor.rowcount
against returned rows, and only rowcount=0 with no rows is the valid no-work
claim result
(src/parallax/domains/token_intel/repositories/projection_repository.py:305,
src/parallax/domains/token_intel/repositories/projection_repository.py:326,
src/parallax/domains/token_intel/repositories/projection_repository.py:327,
src/parallax/domains/token_intel/repositories/projection_repository.py:410,
src/parallax/domains/token_intel/repositories/projection_repository.py:420,
src/parallax/domains/token_intel/repositories/projection_repository.py:422,
tests/unit/domains/token_intel/test_projection_repository.py:77,
tests/unit/domains/token_intel/test_projection_repository.py:90,
tests/unit/domains/token_intel/test_projection_repository.py:102,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:898,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:911,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:916).

Follow-up review found the remaining ProjectionRepository control-plane writes
needed the same execution evidence. advance_offset, finish_run, and
enqueue_dirty_range now save their write cursor and require
_required_single_rowcount(cursor), while start_run starts a run through
INSERT INTO projection_runs plus RETURNING *, fetches from the saved cursor,
and returns only through _required_returning_row(cursor, row) instead of
run_by_id readback
(src/parallax/domains/token_intel/repositories/projection_repository.py:46,
src/parallax/domains/token_intel/repositories/projection_repository.py:62,
src/parallax/domains/token_intel/repositories/projection_repository.py:94,
src/parallax/domains/token_intel/repositories/projection_repository.py:119,
src/parallax/domains/token_intel/repositories/projection_repository.py:121,
src/parallax/domains/token_intel/repositories/projection_repository.py:126,
src/parallax/domains/token_intel/repositories/projection_repository.py:138,
src/parallax/domains/token_intel/repositories/projection_repository.py:139,
src/parallax/domains/token_intel/repositories/projection_repository.py:175,
src/parallax/domains/token_intel/repositories/projection_repository.py:187,
src/parallax/domains/token_intel/repositories/projection_repository.py:208,
src/parallax/domains/token_intel/repositories/projection_repository.py:212,
src/parallax/domains/token_intel/repositories/projection_repository.py:234,
src/parallax/domains/token_intel/repositories/projection_repository.py:262,
src/parallax/domains/token_intel/repositories/projection_repository.py:291,
src/parallax/domains/token_intel/repositories/projection_repository.py:427,
src/parallax/domains/token_intel/repositories/projection_repository.py:434,
tests/unit/domains/token_intel/test_projection_repository.py:117,
tests/unit/domains/token_intel/test_projection_repository.py:126,
tests/unit/domains/token_intel/test_projection_repository.py:139,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:923,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:933,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:943,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:958).

Follow-up review found Token Radar narrative hydration still had an API-layer
target-identity shape bridge. The route now passes the AssetFlowService
payload directly into hydrate_token_radar, while NarrativeReadModel reads
the formal public row target object through _target_identity(row) before
digest lookup; the route guard forbids _synthetic_target_type,
_synthetic_target_id, _with_top_level_targets, and _strip_synthetic_targets
from returning
(src/parallax/app/surfaces/api/routes_radar.py:101,
src/parallax/app/surfaces/api/routes_radar.py:111,
src/parallax/app/surfaces/api/routes_radar.py:112,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:14,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:98,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:115,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:121,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:122,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:123,
src/parallax/domains/narrative_intel/read_models/narrative_read_model.py:124,
tests/unit/domains/narrative_intel/test_narrative_read_model.py:66,
tests/unit/domains/narrative_intel/test_narrative_read_model.py:85,
tests/unit/test_api_narrative_contract.py:177,
tests/unit/test_api_narrative_contract.py:181,
tests/unit/test_api_narrative_contract.py:183,
tests/architecture/test_api_read_paths_provider_free.py:361,
tests/architecture/test_api_read_paths_provider_free.py:365,
tests/architecture/test_api_read_paths_provider_free.py:366,
tests/architecture/test_api_read_paths_provider_free.py:368,
tests/architecture/test_api_read_paths_provider_free.py:370,
tests/architecture/test_api_read_paths_provider_free.py:371,
tests/architecture/test_api_read_paths_provider_free.py:380,
tests/architecture/test_api_read_paths_provider_free.py:381).

Follow-up review found the same required-write evidence gap in Asset Market
registry facts. In RegistryRepository, upsert_cex_token,
upsert_chain_asset, upsert_pricefeed, and upsert_us_equity_symbol now
capture the PostgreSQL cursor, fetch one returned row, and return only through
_required_returning_row(cursor, row); CEX token, price-feed, and US equity
symbol upserts use RETURNING *, while the chain-asset CTE result also requires
rowcount=1 with a returned row
(src/parallax/domains/asset_market/repositories/registry_repository.py:10,
src/parallax/domains/asset_market/repositories/registry_repository.py:14,
src/parallax/domains/asset_market/repositories/registry_repository.py:34,
src/parallax/domains/asset_market/repositories/registry_repository.py:47,
src/parallax/domains/asset_market/repositories/registry_repository.py:51,
src/parallax/domains/asset_market/repositories/registry_repository.py:52,
src/parallax/domains/asset_market/repositories/registry_repository.py:54,
src/parallax/domains/asset_market/repositories/registry_repository.py:80,
src/parallax/domains/asset_market/repositories/registry_repository.py:108,
src/parallax/domains/asset_market/repositories/registry_repository.py:123,
src/parallax/domains/asset_market/repositories/registry_repository.py:152,
src/parallax/domains/asset_market/repositories/registry_repository.py:153,
src/parallax/domains/asset_market/repositories/registry_repository.py:155,
src/parallax/domains/asset_market/repositories/registry_repository.py:205,
src/parallax/domains/asset_market/repositories/registry_repository.py:226,
src/parallax/domains/asset_market/repositories/registry_repository.py:247,
src/parallax/domains/asset_market/repositories/registry_repository.py:248,
src/parallax/domains/asset_market/repositories/registry_repository.py:250,
src/parallax/domains/asset_market/repositories/registry_repository.py:278,
src/parallax/domains/asset_market/repositories/registry_repository.py:295,
src/parallax/domains/asset_market/repositories/registry_repository.py:310,
src/parallax/domains/asset_market/repositories/registry_repository.py:311).
The shared _required_returning_row helper reads _cursor_rowcount(cursor),
fails missing rowcount as registry_repository_rowcount_required, fails
non-one or missing-row evidence as registry_repository_rowcount_invalid, and
the architecture guard forbids _row_by_id, return dict(row) if row else {},
and ) or {} from reappearing
(src/parallax/domains/asset_market/repositories/registry_repository.py:779,
src/parallax/domains/asset_market/repositories/registry_repository.py:783,
src/parallax/domains/asset_market/repositories/registry_repository.py:798,
src/parallax/domains/asset_market/repositories/registry_repository.py:799,
src/parallax/domains/asset_market/repositories/registry_repository.py:800,
src/parallax/domains/asset_market/repositories/registry_repository.py:801,
src/parallax/domains/asset_market/repositories/registry_repository.py:802,
src/parallax/domains/asset_market/repositories/registry_repository.py:803,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1164,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1165,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1166,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1167,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1168,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1169,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1170,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1172,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1173,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1174,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1175,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1176,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1177,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1179,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1180,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1181,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1182,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:1183).
Unit tests cover missing rowcount, invalid or unexpected rowcount, and
rowcount=1 with no returned row for all four registry upsert operations
(tests/unit/test_registry_repository.py:219,
tests/unit/test_registry_repository.py:220,
tests/unit/test_registry_repository.py:223,
tests/unit/test_registry_repository.py:227,
tests/unit/test_registry_repository.py:228,
tests/unit/test_registry_repository.py:229,
tests/unit/test_registry_repository.py:235,
tests/unit/test_registry_repository.py:239,
tests/unit/test_registry_repository.py:240,
tests/unit/test_registry_repository.py:245).

Follow-up review found the same rowcount evidence gap in News projection
dirty-target terminalization. terminalize_targets deletes claimed
news_projection_dirty_targets through _delete_claimed_target_rows(records),
where cursor.fetchall() returns deleted rows, _returned_rowcount(cursor, rows)
validates PostgreSQL cursor.rowcount, and only then may
terminalize_source_row write terminal ledger evidence; the returned terminal
count is the validated deleted_count
(src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:383,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:275,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:278,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:300,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:309,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:313,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:314,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:398,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:402,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:413,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:418).
The terminalize_targets target contract is that _returned_rowcount reads
PostgreSQL cursor.rowcount, fails missing rowcount as
news_projection_dirty_target_rowcount_required, fails invalid or mismatched
rowcount as news_projection_dirty_target_rowcount_invalid, and tests plus
architecture guards prove news_projection_dirty_targets terminal ledger writes
are blocked before malformed RETURNING count evidence is trusted
(src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:383,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:413,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:660,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:661,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:662,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:663,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:628,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:629,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:257,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:272,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:284,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:301,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:310,
tests/architecture/test_news_intel_kiss_simplification.py:412,
tests/architecture/test_news_intel_kiss_simplification.py:425,
tests/architecture/test_news_intel_kiss_simplification.py:431,
tests/architecture/test_news_intel_kiss_simplification.py:433,
tests/architecture/test_news_intel_kiss_simplification.py:434).

Follow-up review found the same single-row rowcount evidence gap at the Evidence
fact ingress boundary. insert_raw_frame and
insert_event_without_commit now classify raw_frames and events
conflict-ignore results only through _single_rowcount(cursor) == 1,
and _single_rowcount fails missing or invalid PostgreSQL rowcount evidence as
evidence_repository_rowcount_required or
evidence_repository_rowcount_invalid
(src/parallax/domains/evidence/repositories/evidence_repository.py:30,
src/parallax/domains/evidence/repositories/evidence_repository.py:45,
src/parallax/domains/evidence/repositories/evidence_repository.py:53,
src/parallax/domains/evidence/repositories/evidence_repository.py:63,
src/parallax/domains/evidence/repositories/evidence_repository.py:66,
src/parallax/domains/evidence/repositories/evidence_repository.py:88,
src/parallax/domains/evidence/repositories/evidence_repository.py:391,
src/parallax/domains/evidence/repositories/evidence_repository.py:393,
src/parallax/domains/evidence/repositories/evidence_repository.py:395,
src/parallax/domains/evidence/repositories/evidence_repository.py:397,
src/parallax/domains/evidence/repositories/evidence_repository.py:399).
insert_event_entities now counts event_entities writes from the same
single-row rowcount contract, failing as
entity_repository_rowcount_required or entity_repository_rowcount_invalid
before inserted-entity counts are returned
(src/parallax/domains/evidence/repositories/entity_repository.py:17,
src/parallax/domains/evidence/repositories/entity_repository.py:32,
src/parallax/domains/evidence/repositories/entity_repository.py:62,
src/parallax/domains/evidence/repositories/entity_repository.py:176,
src/parallax/domains/evidence/repositories/entity_repository.py:180,
src/parallax/domains/evidence/repositories/entity_repository.py:182).
Unit tests cover missing, boolean, string, None, negative, and multi-row
rowcount values across raw-frame, event, and event-entity writes, and the
architecture guard rejects bare/default rowcount classification
(tests/unit/domains/evidence/test_evidence_repositories.py:115,
tests/unit/domains/evidence/test_evidence_repositories.py:116,
tests/unit/domains/evidence/test_evidence_repositories.py:127,
tests/unit/domains/evidence/test_evidence_repositories.py:128,
tests/unit/domains/evidence/test_evidence_repositories.py:179,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:857,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:858,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:859,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:860,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:864,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:865,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:866,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:867,
tests/architecture/test_runtime_worker_constraint_hard_cut.py:868).

Follow-up review found that CEX read-model rowcount helpers still preserved a
post-hard-cut compatibility conversion. CexOiRadarRepository accounts for
board delete/upsert writes through _cursor_rowcount(delete_cursor) and
_cursor_rowcount(upsert_cursor), and _cursor_rowcount now rejects missing,
boolean, negative, and non-integer cursor.rowcount before board write counts
are returned
(src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:22,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:203,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:277,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:410,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:412,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:414,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:415,
src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py:417).
CexDetailSnapshotRepository accounts for snapshot upserts through
_rowcount(cursor), and CexDerivativeSeriesRepository accounts for derivative
series upserts through _cursor_rowcount(cursor) with the same non-boolean
non-negative integer rowcount contract
(src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:31,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:123,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:295,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:297,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:299,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:300,
src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py:302,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:11,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:83,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:132,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:134,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:136,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:137,
src/parallax/domains/cex_market_intel/repositories/cex_derivative_series_repository.py:139).
Unit tests cover string, boolean, and negative rowcount for board/detail paths
and missing/string/bool/negative rowcount for derivative series, while the
architecture guard rejects restoring return max(0, int(rowcount)) or
return max(int(rowcount), 0) compatibility
(tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py:465,
tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py:483,
tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py:393,
tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py:405,
tests/unit/domains/cex_market_intel/test_cex_derivative_series_repository.py:87,
tests/unit/domains/cex_market_intel/test_cex_derivative_series_repository.py:99,
tests/architecture/test_cex_oi_kappa_contract.py:26,
tests/architecture/test_cex_oi_kappa_contract.py:29,
tests/architecture/test_cex_oi_kappa_contract.py:102,
tests/architecture/test_cex_oi_kappa_contract.py:105,
tests/architecture/test_cex_oi_kappa_contract.py:189,
tests/architecture/test_cex_oi_kappa_contract.py:192).

Follow-up review found the same rowcount conversion gap in Token Radar write
count helpers after the default-rowcount hard cut. TokenRadarRepository,
TokenRadarDirtyTargetRepository, TokenRadarSourceDirtyEventRepository, and
TokenRadarRankSourceQuery now require cursor.rowcount to be a non-boolean
non-negative integer and reject numeric strings before current-row publication,
target/source dirty queue accounting, or rank-source prune counts are returned
(src/parallax/domains/token_intel/repositories/token_radar_repository.py:84,
src/parallax/domains/token_intel/repositories/token_radar_repository.py:1301,
src/parallax/domains/token_intel/repositories/token_radar_repository.py:1303,
src/parallax/domains/token_intel/repositories/token_radar_repository.py:1305,
src/parallax/domains/token_intel/repositories/token_radar_repository.py:1306,
src/parallax/domains/token_intel/repositories/token_radar_repository.py:1308,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:39,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:357,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:359,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:361,
src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:362,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:15,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:439,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:441,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:443,
src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:444,
src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:35,
src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:265,
src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:267,
src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:269,
src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:270).
Unit tests cover numeric-string rowcount for current-row publication,
target-feature writes, target dirty queue writes, source dirty queue writes, and
rank-source prune writes. Architecture guards reject restoring
count = int(rowcount) at those cursor rowcount boundaries while preserving
explicit SQL aggregate count evidence for rank-source population
(tests/unit/test_token_radar_repository.py:554,
tests/unit/test_token_radar_repository.py:895,
tests/unit/test_token_radar_dirty_target_repository.py:215,
tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py:181,
tests/unit/domains/token_intel/test_token_radar_rank_source_query.py:364,
tests/architecture/test_token_radar_publication_state_hard_cut.py:771,
tests/architecture/test_token_radar_publication_state_hard_cut.py:775,
tests/architecture/test_token_radar_publication_state_hard_cut.py:776,
tests/architecture/test_token_radar_source_width_contract.py:243,
tests/architecture/test_token_radar_source_width_contract.py:247,
tests/architecture/test_token_radar_source_width_contract.py:248,
tests/architecture/test_token_radar_source_width_contract.py:308,
tests/architecture/test_token_radar_source_width_contract.py:314,
tests/architecture/test_token_radar_source_width_contract.py:315).

Follow-up review found the same returned-row-only classification gap in News
page read-model writes. replace_page_rows_for_items writes news_page_rows
through RETURNING (xmax = 0) and must classify inserted, updated, and
unchanged results only after _optional_returning_row validates real
PostgreSQL cursor.rowcount against returned-row presence
(src/parallax/domains/news_intel/repositories/news_repository.py:5042,
src/parallax/domains/news_intel/repositories/news_repository.py:5082,
src/parallax/domains/news_intel/repositories/news_repository.py:5146,
src/parallax/domains/news_intel/repositories/news_repository.py:5151,
src/parallax/domains/news_intel/repositories/news_repository.py:5341).
Unit and architecture coverage now require missing/invalid/mismatched rowcount
to fail before page-row inserted/updated/unchanged accounting, while accepting
the only unchanged projection shape as rowcount 0 with no returned row
(tests/unit/domains/news_intel/test_news_repository_queries.py:1315,
tests/unit/domains/news_intel/test_news_repository_queries.py:1324,
tests/unit/domains/news_intel/test_news_repository_queries.py:1332,
tests/unit/domains/news_intel/test_news_repository_queries.py:1341,
tests/architecture/test_news_intel_kiss_simplification.py:838,
tests/architecture/test_news_intel_kiss_simplification.py:852,
tests/architecture/test_news_intel_kiss_simplification.py:856,
tests/architecture/test_news_intel_kiss_simplification.py:857,
tests/architecture/test_news_intel_kiss_simplification.py:858).

Follow-up review found the same returned-row-only evidence gap in News fetch
source claims. claim_due_sources owns the UPDATE news_sources AS sources
and RETURNING sources.* source-claim path used before provider fetch work
starts (src/parallax/domains/news_intel/repositories/news_repository.py:472,
src/parallax/domains/news_intel/repositories/news_repository.py:477), and its
target contract is to capture the cursor, fetch returned source rows, validate
_returned_rowcount(cursor, rows), and return due-source claim rows only after
cursor rowcount matches the returned row count. Missing rowcount fails as
news_repository_rowcount_required; invalid or mismatched rowcount fails as
news_repository_rowcount_invalid; architecture coverage rejects restored chained
.fetchall() or returned-list-length accounting
(src/parallax/domains/news_intel/repositories/news_repository.py:453,
src/parallax/domains/news_intel/ARCHITECTURE.md:118,
src/parallax/domains/news_intel/repositories/news_repository.py:477,
src/parallax/domains/news_intel/repositories/news_repository.py:486,
src/parallax/domains/news_intel/repositories/news_repository.py:487,
src/parallax/domains/news_intel/repositories/news_repository.py:5056,
src/parallax/domains/news_intel/repositories/news_repository.py:5060,
src/parallax/domains/news_intel/repositories/news_repository.py:5062,
src/parallax/domains/news_intel/repositories/news_repository.py:5075,
src/parallax/domains/news_intel/repositories/news_repository.py:5076,
src/parallax/domains/news_intel/repositories/news_repository.py:5078,
tests/unit/domains/news_intel/test_news_repository_queries.py:742,
tests/unit/domains/news_intel/test_news_repository_queries.py:759,
tests/architecture/test_news_intel_kiss_simplification.py:544,
tests/architecture/test_news_intel_kiss_simplification.py:559,
tests/architecture/test_news_intel_kiss_simplification.py:561,
tests/architecture/test_news_intel_kiss_simplification.py:564).

Follow-up review found the same returned-row-only evidence gap in News
fetch-run finalization. finish_fetch_run writes UPDATE news_fetch_runs,
reads row = cursor.fetchone(), and must validate
_required_returning_row(cursor, row) before UPDATE news_sources or
return returned_row; the helper calls _optional_returning_row
and fails malformed required-row evidence as
news_repository_rowcount_invalid. Unit coverage requires missing rowcount,
invalid/mismatched rowcount, missing required rows, and matching single-row
success to preserve that order; architecture coverage rejects chained
).fetchone(), return dict(row), and rowcount-default restoration
(src/parallax/domains/news_intel/repositories/news_repository.py:514,
src/parallax/domains/news_intel/repositories/news_repository.py:537,
src/parallax/domains/news_intel/repositories/news_repository.py:539,
src/parallax/domains/news_intel/repositories/news_repository.py:550,
src/parallax/domains/news_intel/repositories/news_repository.py:565,
src/parallax/domains/news_intel/repositories/news_repository.py:566,
src/parallax/domains/news_intel/repositories/news_repository.py:570,
src/parallax/domains/news_intel/repositories/news_repository.py:592,
src/parallax/domains/news_intel/repositories/news_repository.py:5073,
src/parallax/domains/news_intel/repositories/news_repository.py:5097,
src/parallax/domains/news_intel/repositories/news_repository.py:5099,
src/parallax/domains/news_intel/repositories/news_repository.py:5100,
src/parallax/domains/news_intel/repositories/news_repository.py:5093,
src/parallax/domains/news_intel/repositories/news_repository.py:5094,
src/parallax/domains/news_intel/repositories/news_repository.py:5096,
src/parallax/domains/news_intel/repositories/news_repository.py:5341,
src/parallax/domains/news_intel/repositories/news_repository.py:5385,
src/parallax/domains/news_intel/repositories/news_repository.py:5351,
tests/unit/domains/news_intel/test_news_repository_queries.py:912,
tests/unit/domains/news_intel/test_news_repository_queries.py:922,
tests/unit/domains/news_intel/test_news_repository_queries.py:935,
tests/unit/domains/news_intel/test_news_repository_queries.py:946,
tests/architecture/test_news_intel_kiss_simplification.py:753,
tests/architecture/test_news_intel_kiss_simplification.py:787,
tests/architecture/test_news_intel_kiss_simplification.py:759,
tests/architecture/test_news_intel_kiss_simplification.py:760,
tests/architecture/test_news_intel_kiss_simplification.py:768,
tests/architecture/test_news_intel_kiss_simplification.py:772,
tests/architecture/test_news_intel_kiss_simplification.py:774).

Follow-up review found the same execution-evidence gap at News fetch-run start.
start_fetch_run writes INSERT INTO news_fetch_runs, validates
_required_rowcount(cursor, expected=1) before UPDATE news_sources, validates
the same helper again before return fetch_run_id, and the helper reads
_cursor_rowcount(cursor) before failing invalid counts as
news_repository_rowcount_invalid. Unit coverage requires missing/invalid
insert and source-update rowcounts to fail in order, and architecture coverage
keeps both required rowcount checks in the start path
(src/parallax/domains/news_intel/repositories/news_repository.py:491,
src/parallax/domains/news_intel/repositories/news_repository.py:495,
src/parallax/domains/news_intel/repositories/news_repository.py:500,
src/parallax/domains/news_intel/repositories/news_repository.py:503,
src/parallax/domains/news_intel/repositories/news_repository.py:510,
src/parallax/domains/news_intel/repositories/news_repository.py:511,
src/parallax/domains/news_intel/repositories/news_repository.py:5068,
src/parallax/domains/news_intel/repositories/news_repository.py:5069,
src/parallax/domains/news_intel/repositories/news_repository.py:5071,
src/parallax/domains/news_intel/repositories/news_repository.py:5073,
src/parallax/domains/news_intel/repositories/news_repository.py:5074,
src/parallax/domains/news_intel/repositories/news_repository.py:5077,
src/parallax/domains/news_intel/repositories/news_repository.py:5079,
tests/unit/domains/news_intel/test_news_repository_queries.py:854,
tests/unit/domains/news_intel/test_news_repository_queries.py:865,
tests/unit/domains/news_intel/test_news_repository_queries.py:877,
tests/unit/domains/news_intel/test_news_repository_queries.py:888,
tests/unit/domains/news_intel/test_news_repository_queries.py:900,
tests/architecture/test_news_intel_kiss_simplification.py:777,
tests/architecture/test_news_intel_kiss_simplification.py:791,
tests/architecture/test_news_intel_kiss_simplification.py:792,
tests/architecture/test_news_intel_kiss_simplification.py:794,
tests/architecture/test_news_intel_kiss_simplification.py:796,
tests/architecture/test_news_intel_kiss_simplification.py:797,
tests/architecture/test_news_intel_kiss_simplification.py:798).

Follow-up review found the same RETURNING-row evidence gap one step earlier in
News configured-source reconciliation. upsert_source writes
INSERT INTO news_sources, reads row = cursor.fetchone(), then validates
_required_returning_row(cursor, row) before return {**returned_row, "status": status}.
The required helper delegates to _optional_returning_row, so
missing rowcount fails as a required-rowcount error and no-row or rowcount/row
mismatch fails as invalid rowcount. Unit coverage now requires missing,
invalid/mismatched, and no-row source upsert results to fail, and architecture
coverage keeps the source write segment from restoring chained fetchone or
dict(row) success paths
(src/parallax/domains/news_intel/repositories/news_repository.py:230,
src/parallax/domains/news_intel/repositories/news_repository.py:279,
src/parallax/domains/news_intel/repositories/news_repository.py:281,
src/parallax/domains/news_intel/repositories/news_repository.py:304,
src/parallax/domains/news_intel/repositories/news_repository.py:326,
src/parallax/domains/news_intel/repositories/news_repository.py:327,
src/parallax/domains/news_intel/repositories/news_repository.py:328,
src/parallax/domains/news_intel/repositories/news_repository.py:5084,
src/parallax/domains/news_intel/repositories/news_repository.py:5085,
src/parallax/domains/news_intel/repositories/news_repository.py:5097,
src/parallax/domains/news_intel/repositories/news_repository.py:5100,
src/parallax/domains/news_intel/repositories/news_repository.py:5093,
src/parallax/domains/news_intel/repositories/news_repository.py:5094,
src/parallax/domains/news_intel/repositories/news_repository.py:5341,
src/parallax/domains/news_intel/repositories/news_repository.py:5351,
tests/unit/domains/news_intel/test_news_repository_queries.py:367,
tests/unit/domains/news_intel/test_news_repository_queries.py:382,
tests/unit/domains/news_intel/test_news_repository_queries.py:398,
tests/unit/domains/news_intel/test_news_repository_queries.py:409,
tests/architecture/test_news_intel_kiss_simplification.py:568,
tests/architecture/test_news_intel_kiss_simplification.py:572,
tests/architecture/test_news_intel_kiss_simplification.py:576,
tests/architecture/test_news_intel_kiss_simplification.py:578,
tests/architecture/test_news_intel_kiss_simplification.py:582,
tests/architecture/test_news_intel_kiss_simplification.py:588,
tests/architecture/test_news_intel_kiss_simplification.py:591).

Follow-up review found the same required-row evidence gap at the News provider
observation boundary. upsert_provider_item persists provider observations
through INSERT INTO news_provider_items, captures
cursor = self.conn.execute, reads row = cursor.fetchone(), validates
_required_returning_row(cursor, row), and returns
return {**returned_row, "status": status, "incoming_provider_payload_status": incoming_payload_status}.
That makes inserted/updated provider-item outcomes require rowcount=1 with one
returned row, while duplicate/no-material-change still returns the already-read
existing row without running the write. Unit coverage now requires missing,
invalid/mismatched, and no-row provider-item upserts to fail, and architecture
coverage forbids restoring chained fetchone or dict(row) success in the
provider-item write segment
(src/parallax/domains/news_intel/repositories/news_repository.py:675,
src/parallax/domains/news_intel/repositories/news_repository.py:806,
src/parallax/domains/news_intel/repositories/news_repository.py:808,
src/parallax/domains/news_intel/repositories/news_repository.py:851,
src/parallax/domains/news_intel/repositories/news_repository.py:869,
src/parallax/domains/news_intel/repositories/news_repository.py:870,
src/parallax/domains/news_intel/repositories/news_repository.py:871,
src/parallax/domains/news_intel/repositories/news_repository.py:5084,
src/parallax/domains/news_intel/repositories/news_repository.py:5093,
src/parallax/domains/news_intel/repositories/news_repository.py:5094,
tests/unit/domains/news_intel/test_news_repository_queries.py:425,
tests/unit/domains/news_intel/test_news_repository_queries.py:440,
tests/unit/domains/news_intel/test_news_repository_queries.py:458,
tests/unit/domains/news_intel/test_news_repository_queries.py:469,
tests/architecture/test_news_intel_kiss_simplification.py:594,
tests/architecture/test_news_intel_kiss_simplification.py:601,
tests/architecture/test_news_intel_kiss_simplification.py:602,
tests/architecture/test_news_intel_kiss_simplification.py:604,
tests/architecture/test_news_intel_kiss_simplification.py:608,
tests/architecture/test_news_intel_kiss_simplification.py:612,
tests/architecture/test_news_intel_kiss_simplification.py:613,
tests/architecture/test_news_intel_kiss_simplification.py:614,
tests/architecture/test_news_intel_kiss_simplification.py:615,
tests/architecture/test_news_intel_kiss_simplification.py:616,
tests/architecture/test_news_intel_kiss_simplification.py:618).

Follow-up review found the same required-row evidence gap at the News canonical
item merge boundary. upsert_canonical_news_item persists canonical product
facts through INSERT INTO news_items, captures cursor = self.conn.execute,
reads row = cursor.fetchone(), validates
_required_returning_row(cursor, row), and uses
str(returned_row["news_item_id"]) before observation-edge writes, remap cleanup,
and summary refresh can continue. Unit coverage now requires missing,
invalid/mismatched, and no-row canonical item upsert results to fail, and
architecture coverage forbids restoring chained fetchone or rowcount-default
success in the canonical item write segment
(src/parallax/domains/news_intel/repositories/news_repository.py:874,
src/parallax/domains/news_intel/repositories/news_repository.py:1111,
src/parallax/domains/news_intel/repositories/news_repository.py:1113,
src/parallax/domains/news_intel/repositories/news_repository.py:1199,
src/parallax/domains/news_intel/repositories/news_repository.py:1227,
src/parallax/domains/news_intel/repositories/news_repository.py:1228,
src/parallax/domains/news_intel/repositories/news_repository.py:1248,
src/parallax/domains/news_intel/repositories/news_repository.py:1290,
src/parallax/domains/news_intel/repositories/news_repository.py:1298,
src/parallax/domains/news_intel/repositories/news_repository.py:1306,
src/parallax/domains/news_intel/repositories/news_repository.py:5084,
src/parallax/domains/news_intel/repositories/news_repository.py:5093,
src/parallax/domains/news_intel/repositories/news_repository.py:5094,
tests/unit/domains/news_intel/test_news_repository_queries.py:486,
tests/unit/domains/news_intel/test_news_repository_queries.py:499,
tests/unit/domains/news_intel/test_news_repository_queries.py:515,
tests/unit/domains/news_intel/test_news_repository_queries.py:525,
tests/architecture/test_news_intel_kiss_simplification.py:623,
tests/architecture/test_news_intel_kiss_simplification.py:637,
tests/architecture/test_news_intel_kiss_simplification.py:641,
tests/architecture/test_news_intel_kiss_simplification.py:642,
tests/architecture/test_news_intel_kiss_simplification.py:643,
tests/architecture/test_news_intel_kiss_simplification.py:644,
tests/architecture/test_news_intel_kiss_simplification.py:645,
tests/architecture/test_news_intel_kiss_simplification.py:646).

Follow-up review then found the same execution-evidence gap on the observation
edge hop itself. upsert_canonical_news_item now captures the
news_item_observation_edges cursor, validates
_required_rowcount(cursor, expected=1), and unit/architecture coverage requires
missing, invalid, zero, or multi-row edge evidence to fail before provider-article
remap, material duplicate remap, summary refresh, or affected-item accounting can
treat the provider observation as linked
(src/parallax/domains/news_intel/repositories/news_repository.py:874,
src/parallax/domains/news_intel/repositories/news_repository.py:1256,
src/parallax/domains/news_intel/repositories/news_repository.py:1258,
src/parallax/domains/news_intel/repositories/news_repository.py:1286,
src/parallax/domains/news_intel/repositories/news_repository.py:5068,
src/parallax/domains/news_intel/repositories/news_repository.py:5069,
src/parallax/domains/news_intel/repositories/news_repository.py:5071,
tests/unit/domains/news_intel/test_news_repository_queries.py:540,
tests/unit/domains/news_intel/test_news_repository_queries.py:554,
tests/unit/domains/news_intel/test_news_repository_queries.py:569,
tests/architecture/test_news_intel_kiss_simplification.py:649,
tests/architecture/test_news_intel_kiss_simplification.py:664,
tests/architecture/test_news_intel_kiss_simplification.py:669).

Follow-up review found the next hop after observation-edge linking had the same
returned-row-only compatibility shape. _refresh_news_item_observation_summary
now captures the UPDATE news_items / RETURNING items.* cursor, reads
row = cursor.fetchone(), validates _required_returning_row(cursor, row) for
the current canonical item, and uses _optional_returning_row only
for explicit old zero-edge cleanup through required=False. Unit and architecture
coverage require missing/invalid/mismatched rowcount and no required row to fail,
and forbid fallback SELECT readback in the summary refresh path
(src/parallax/domains/news_intel/repositories/news_repository.py:1681,
src/parallax/domains/news_intel/repositories/news_repository.py:1686,
src/parallax/domains/news_intel/repositories/news_repository.py:1688,
src/parallax/domains/news_intel/repositories/news_repository.py:1709,
src/parallax/domains/news_intel/repositories/news_repository.py:1717,
src/parallax/domains/news_intel/repositories/news_repository.py:1721,
src/parallax/domains/news_intel/repositories/news_repository.py:1723,
src/parallax/domains/news_intel/repositories/news_repository.py:1724,
src/parallax/domains/news_intel/repositories/news_repository.py:1344,
src/parallax/domains/news_intel/repositories/news_repository.py:5351,
tests/unit/domains/news_intel/test_news_repository_queries.py:583,
tests/unit/domains/news_intel/test_news_repository_queries.py:596,
tests/unit/domains/news_intel/test_news_repository_queries.py:612,
tests/unit/domains/news_intel/test_news_repository_queries.py:626,
tests/unit/domains/news_intel/test_news_repository_queries.py:640,
tests/unit/domains/news_intel/test_news_repository_queries.py:651,
tests/architecture/test_news_intel_kiss_simplification.py:672,
tests/architecture/test_news_intel_kiss_simplification.py:680,
tests/architecture/test_news_intel_kiss_simplification.py:682,
tests/architecture/test_news_intel_kiss_simplification.py:697,
tests/architecture/test_news_intel_kiss_simplification.py:698).

Follow-up review found the same returned-list-only evidence gap in the canonical
edge-remap helpers. _remap_material_duplicate_edges_to_news_item and
_remap_provider_article_edges_to_news_item both update
news_item_observation_edges, return old item ids through
RETURNING remapped.old_news_item_id, fetch rows = cursor.fetchall(), and now
validate _returned_rowcount(cursor, rows) before returning those old ids to
old-item summary cleanup, dirty-target remap, zero-edge cleanup, or affected-item
accounting. Unit coverage requires missing, invalid, and mismatched rowcount to
fail for both remap helpers, while architecture coverage rejects restored
chained .fetchall() or direct old item-id returned-row accounting
(src/parallax/domains/news_intel/repositories/news_repository.py:1538,
src/parallax/domains/news_intel/repositories/news_repository.py:1582,
src/parallax/domains/news_intel/repositories/news_repository.py:1591,
src/parallax/domains/news_intel/repositories/news_repository.py:1607,
src/parallax/domains/news_intel/repositories/news_repository.py:1625,
src/parallax/domains/news_intel/repositories/news_repository.py:1626,
src/parallax/domains/news_intel/repositories/news_repository.py:1630,
src/parallax/domains/news_intel/repositories/news_repository.py:1638,
src/parallax/domains/news_intel/repositories/news_repository.py:1647,
src/parallax/domains/news_intel/repositories/news_repository.py:1660,
src/parallax/domains/news_intel/repositories/news_repository.py:1676,
src/parallax/domains/news_intel/repositories/news_repository.py:1677,
src/parallax/domains/news_intel/repositories/news_repository.py:5075,
src/parallax/domains/news_intel/repositories/news_repository.py:5076,
src/parallax/domains/news_intel/repositories/news_repository.py:5078,
tests/unit/domains/news_intel/test_news_repository_queries.py:658,
tests/unit/domains/news_intel/test_news_repository_queries.py:675,
tests/unit/domains/news_intel/test_news_repository_queries.py:726,
tests/unit/domains/news_intel/test_news_repository_queries.py:740,
tests/architecture/test_news_intel_kiss_simplification.py:702,
tests/architecture/test_news_intel_kiss_simplification.py:716,
tests/architecture/test_news_intel_kiss_simplification.py:717,
tests/architecture/test_news_intel_kiss_simplification.py:719,
tests/architecture/test_news_intel_kiss_simplification.py:720,
tests/architecture/test_news_intel_kiss_simplification.py:723).

Follow-up review found the same required-row evidence gap at the News item-brief
agent ledger/current boundary. insert_news_item_agent_run now captures the
news_item_agent_runs INSERT ... RETURNING * cursor, reads
row = cursor.fetchone(), validates _required_returning_row(cursor, row), and
returns only that validated ledger row. upsert_news_item_agent_brief applies
the same required single-row contract to news_item_agent_briefs current upserts
before page dirty fan-out, publication eligibility, or returned current rows can
advance. Unit coverage requires missing rowcount, invalid/mismatched rowcount,
missing required rows, and matching single-row results for both paths, including
the explicit news_repository_rowcount_required and
news_repository_rowcount_invalid errors; architecture coverage forbids
restoring chained fetchone or dict(row) success paths
(src/parallax/domains/news_intel/ARCHITECTURE.md:126,
src/parallax/domains/news_intel/repositories/news_repository.py:2053,
src/parallax/domains/news_intel/repositories/news_repository.py:2055,
src/parallax/domains/news_intel/repositories/news_repository.py:2074,
src/parallax/domains/news_intel/repositories/news_repository.py:2078,
src/parallax/domains/news_intel/repositories/news_repository.py:2079,
src/parallax/domains/news_intel/repositories/news_repository.py:2080,
src/parallax/domains/news_intel/repositories/news_repository.py:2083,
src/parallax/domains/news_intel/repositories/news_repository.py:2085,
src/parallax/domains/news_intel/repositories/news_repository.py:2111,
src/parallax/domains/news_intel/repositories/news_repository.py:2115,
src/parallax/domains/news_intel/repositories/news_repository.py:2116,
src/parallax/domains/news_intel/repositories/news_repository.py:2117,
src/parallax/domains/news_intel/repositories/news_repository.py:5093,
src/parallax/domains/news_intel/repositories/news_repository.py:5094,
src/parallax/domains/news_intel/repositories/news_repository.py:5096,
src/parallax/domains/news_intel/repositories/news_repository.py:5062,
src/parallax/domains/news_intel/repositories/news_repository.py:5065,
src/parallax/domains/news_intel/repositories/news_repository.py:5068,
tests/unit/domains/news_intel/test_news_repository_queries.py:1350,
tests/unit/domains/news_intel/test_news_repository_queries.py:1363,
tests/unit/domains/news_intel/test_news_repository_queries.py:1379,
tests/unit/domains/news_intel/test_news_repository_queries.py:1389,
tests/unit/domains/news_intel/test_news_repository_queries.py:1403,
tests/unit/domains/news_intel/test_news_repository_queries.py:1416,
tests/unit/domains/news_intel/test_news_repository_queries.py:1432,
tests/unit/domains/news_intel/test_news_repository_queries.py:1442,
tests/architecture/test_news_intel_kiss_simplification.py:765,
tests/architecture/test_news_intel_kiss_simplification.py:760,
tests/architecture/test_news_intel_kiss_simplification.py:767,
tests/architecture/test_news_intel_kiss_simplification.py:768,
tests/architecture/test_news_intel_kiss_simplification.py:769,
tests/architecture/test_news_intel_kiss_simplification.py:770,
tests/architecture/test_news_intel_kiss_simplification.py:772,
tests/architecture/test_news_intel_kiss_simplification.py:773,
tests/architecture/test_news_intel_kiss_simplification.py:774,
tests/architecture/test_news_intel_kiss_simplification.py:776).

Follow-up review found the optional-row evidence gap in the old-item
representative reselection cleanup. _reselect_news_item_representative_from_edges
now captures the UPDATE news_items ... RETURNING items.* cursor, reads
row = cursor.fetchone(), validates _optional_returning_row, and
returns {} only for the explicit rowcount=0/no-row no-representative-edge
cleanup result. Rowcount=1 with a returned row is the only valid representative
fact refresh before item-scoped derived facts are cleared or affected-item
accounting continues. Unit coverage requires missing rowcount,
invalid/mismatched rowcount, rowcount=1/no-row mismatch, explicit zero-row
no-op, and matching single-row refresh with news_repository_rowcount_required
and news_repository_rowcount_invalid failures; architecture coverage forbids
restoring chained fetchone or dict(row) success paths
(src/parallax/domains/news_intel/ARCHITECTURE.md:218,
src/parallax/domains/news_intel/ARCHITECTURE.md:219,
src/parallax/domains/news_intel/repositories/news_repository.py:1964,
src/parallax/domains/news_intel/repositories/news_repository.py:1965,
src/parallax/domains/news_intel/repositories/news_repository.py:1992,
src/parallax/domains/news_intel/repositories/news_repository.py:2044,
src/parallax/domains/news_intel/repositories/news_repository.py:2048,
src/parallax/domains/news_intel/repositories/news_repository.py:2049,
src/parallax/domains/news_intel/repositories/news_repository.py:2050,
src/parallax/domains/news_intel/repositories/news_repository.py:5084,
src/parallax/domains/news_intel/repositories/news_repository.py:5085,
src/parallax/domains/news_intel/repositories/news_repository.py:5089,
src/parallax/domains/news_intel/repositories/news_repository.py:5062,
src/parallax/domains/news_intel/repositories/news_repository.py:5065,
src/parallax/domains/news_intel/repositories/news_repository.py:5067,
src/parallax/domains/news_intel/repositories/news_repository.py:5068,
src/parallax/domains/news_intel/repositories/news_repository.py:5070,
src/parallax/domains/news_intel/repositories/news_repository.py:5351,
tests/unit/domains/news_intel/test_news_repository_queries.py:658,
tests/unit/domains/news_intel/test_news_repository_queries.py:672,
tests/unit/domains/news_intel/test_news_repository_queries.py:688,
tests/unit/domains/news_intel/test_news_repository_queries.py:698,
tests/unit/domains/news_intel/test_news_repository_queries.py:708,
tests/architecture/test_news_intel_kiss_simplification.py:715,
tests/architecture/test_news_intel_kiss_simplification.py:709,
tests/architecture/test_news_intel_kiss_simplification.py:711,
tests/architecture/test_news_intel_kiss_simplification.py:719,
tests/architecture/test_news_intel_kiss_simplification.py:723,
tests/architecture/test_news_intel_kiss_simplification.py:724,
tests/architecture/test_news_intel_kiss_simplification.py:725).

Follow-up review found the same returned-rows evidence gap at the News
item-process claim boundary. claim_unprocessed_items now captures the claim
cursor, updates rows through UPDATE news_items AS items, returns claim payloads
from RETURNING items.*, reads rows = cursor.fetchall(), validates
_returned_rowcount(cursor, rows), and returns claimed_rows only after cursor
rowcount matches the returned rows. Unit coverage requires
news_repository_rowcount_required, news_repository_rowcount_invalid, zero-row
no-op, and matching claim rows; architecture coverage forbids restoring chained
).fetchall() or direct return [dict(row) for row in rows] claim accounting
(src/parallax/domains/news_intel/repositories/news_repository.py:2444,
src/parallax/domains/news_intel/repositories/news_repository.py:2476,
src/parallax/domains/news_intel/repositories/news_repository.py:2486,
src/parallax/domains/news_intel/repositories/news_repository.py:2541,
src/parallax/domains/news_intel/repositories/news_repository.py:2542,
src/parallax/domains/news_intel/repositories/news_repository.py:2543,
src/parallax/domains/news_intel/repositories/news_repository.py:2544,
tests/unit/domains/news_intel/test_news_repository_queries.py:259,
tests/unit/domains/news_intel/test_news_repository_queries.py:266,
tests/unit/domains/news_intel/test_news_repository_queries.py:279,
tests/unit/domains/news_intel/test_news_repository_queries.py:289,
tests/unit/domains/news_intel/test_news_repository_queries.py:301,
tests/unit/domains/news_intel/test_news_repository_queries.py:317,
tests/architecture/test_news_intel_kiss_simplification.py:827,
tests/architecture/test_news_intel_kiss_simplification.py:832,
tests/architecture/test_news_intel_kiss_simplification.py:833,
tests/architecture/test_news_intel_kiss_simplification.py:834,
tests/architecture/test_news_intel_kiss_simplification.py:835,
tests/architecture/test_news_intel_kiss_simplification.py:843,
tests/architecture/test_news_intel_kiss_simplification.py:844,
tests/architecture/test_news_intel_kiss_simplification.py:845,
tests/architecture/test_news_intel_kiss_simplification.py:846,
tests/architecture/test_news_intel_kiss_simplification.py:847).

Follow-up review found the same returned-rows evidence gap at the News current
item-brief schema cleanup boundary. clear_current_briefs_outside_schema
deletes stale current news_item_agent_briefs rows through
DELETE FROM news_item_agent_briefs / RETURNING news_item_id, reads
rows = cursor.fetchall(), validates _returned_rowcount(cursor, rows), and
returns cleared_ids only after cursor rowcount matches the returned ids. Unit
coverage requires news_repository_rowcount_required,
news_repository_rowcount_invalid, zero-row no-op, and matching deleted ids;
architecture coverage forbids restoring chained ).fetchall() or direct
returned-list cleanup accounting
(src/parallax/domains/news_intel/repositories/news_repository.py:2237,
src/parallax/domains/news_intel/repositories/news_repository.py:2255,
src/parallax/domains/news_intel/repositories/news_repository.py:2258,
src/parallax/domains/news_intel/repositories/news_repository.py:2262,
src/parallax/domains/news_intel/repositories/news_repository.py:2263,
src/parallax/domains/news_intel/repositories/news_repository.py:2264,
tests/unit/domains/news_intel/test_news_repository_queries.py:1533,
tests/unit/domains/news_intel/test_news_repository_queries.py:1537,
tests/unit/domains/news_intel/test_news_repository_queries.py:1550,
tests/unit/domains/news_intel/test_news_repository_queries.py:1557,
tests/unit/domains/news_intel/test_news_repository_queries.py:1567,
tests/unit/domains/news_intel/test_news_repository_queries.py:1580,
tests/architecture/test_news_intel_kiss_simplification.py:885,
tests/architecture/test_news_intel_kiss_simplification.py:890,
tests/architecture/test_news_intel_kiss_simplification.py:891,
tests/architecture/test_news_intel_kiss_simplification.py:892,
tests/architecture/test_news_intel_kiss_simplification.py:900,
tests/architecture/test_news_intel_kiss_simplification.py:901,
tests/architecture/test_news_intel_kiss_simplification.py:902,
tests/architecture/test_news_intel_kiss_simplification.py:903).

Follow-up review found the same returned-rows evidence gap at the News
projection dirty-target claim boundary. claim_due claims due
news_projection_dirty_targets with FOR UPDATE SKIP LOCKED,
UPDATE news_projection_dirty_targets, and
RETURNING news_projection_dirty_targets.*,
then reads rows = cursor.fetchall(), validates
_returned_rowcount(cursor, rows), and returns claimed_rows only after cursor
rowcount matches the claim rows. Unit coverage requires
news_projection_dirty_target_rowcount_required,
news_projection_dirty_target_rowcount_invalid, zero-row no-op, and matching
claim rows; architecture coverage forbids restoring chained ).fetchall() or
direct returned-list claim accounting
(src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:165,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:192,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:205,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:207,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:217,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:221,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:222,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:223,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:625,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:627,
src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:628,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:354,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:358,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:366,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:367,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:370,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:377,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:386,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:400,
tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:412,
tests/architecture/test_news_intel_kiss_simplification.py:437,
tests/architecture/test_news_intel_kiss_simplification.py:443,
tests/architecture/test_news_intel_kiss_simplification.py:455,
tests/architecture/test_news_intel_kiss_simplification.py:456,
tests/architecture/test_news_intel_kiss_simplification.py:457,
tests/architecture/test_news_intel_kiss_simplification.py:458,
tests/architecture/test_news_intel_kiss_simplification.py:459,
tests/architecture/test_news_intel_kiss_simplification.py:460,
tests/architecture/test_news_intel_kiss_simplification.py:461,
tests/architecture/test_news_intel_kiss_simplification.py:462).

Follow-up review found the same write-evidence gap in notification fact
aggregation. The notification aggregate helper updates an existing notifications
row after the insert-conflict path reports a dedupe conflict; that aggregate
UPDATE notifications now captures the cursor, validates
_single_row_write_count(, and requires the result to be exactly 1 before
returning aggregate success
(src/parallax/domains/notifications/repositories/notification_repository.py:327,
src/parallax/domains/notifications/repositories/notification_repository.py:329,
src/parallax/domains/notifications/repositories/notification_repository.py:366,
src/parallax/domains/notifications/repositories/notification_repository.py:368,
src/parallax/domains/notifications/repositories/notification_repository.py:369,
src/parallax/domains/notifications/repositories/notification_repository.py:371,
src/parallax/domains/notifications/repositories/notification_repository.py:372,
src/parallax/domains/notifications/repositories/notification_repository.py:373).
The target contract is that missing aggregate rowcount fails as
notification_aggregate_rowcount_required, invalid/zero/multi-row rowcount
fails as notification_aggregate_rowcount_invalid, and tests plus architecture
guards prove aggregate success is no longer inferred from bare UPDATE execution
or readback state
(tests/unit/test_notification_worker_runtime.py:641,
tests/unit/test_notification_worker_runtime.py:645,
tests/unit/test_notification_worker_runtime.py:651,
tests/unit/test_notification_worker_runtime.py:656,
tests/unit/test_notification_worker_runtime.py:662,
tests/unit/test_notification_worker_runtime.py:668,
tests/unit/test_notification_worker_runtime.py:669,
tests/unit/test_notification_worker_runtime.py:671,
tests/unit/test_notification_worker_runtime.py:1213,
tests/unit/test_notification_worker_runtime.py:1245,
tests/unit/test_notification_worker_runtime.py:1247,
tests/unit/test_notification_worker_runtime.py:1248,
tests/unit/test_notification_worker_runtime.py:1279,
tests/architecture/test_notifications_hard_cut.py:407,
tests/architecture/test_notifications_hard_cut.py:418,
tests/architecture/test_notifications_hard_cut.py:419,
tests/architecture/test_notifications_hard_cut.py:423,
tests/architecture/test_notifications_hard_cut.py:424,
tests/architecture/test_notifications_hard_cut.py:425,
tests/architecture/test_notifications_hard_cut.py:426).


Current read and worker paths preserve old compatibility lanes that blur the boundary between provider IO, material facts, rebuildable read models, and maintenance work. This makes the Kappa/CQRS system harder to reason about, adds hidden request-time latency and external dependencies, and leaves several PostgreSQL hot paths vulnerable to table growth (docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:16, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:54, docs/reviews/kappa-cqrs-worker-sql-audit-2026-06-12.md:75, docs/references/POSTGRES_PERFORMANCE.md:10).

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should `/api/stocks-radar` grow a new persisted equity quote worker in this feature? | No. KISS hard cut: remove request-time quote IO now and return an honest unavailable quote block until a separate persisted equity-market lane is specified. | delegated goal | 2026-06-12 |
| Should old helper APIs remain as shims for tests or callers? | No. Delete mixed-path helpers and move tests to the real runtime path or smaller pure functions. | delegated goal | 2026-06-12 |
| Should maintenance cleanup stay inside publication or claim hot paths? | No. Hot paths must only do bounded work needed for the immediate claim or projection. | delegated goal | 2026-06-12 |
| Should JSONB expression indexes be used to preserve broad Pulse handle filtering? | No as a default. Prefer read-model shape or narrower semantics over indexing a compatibility expansion. | delegated goal | 2026-06-12 |
| Should Signal Pulse public health expose whether the runtime worker is currently running? | No. Public Pulse health is persisted read-model/freshness state; scheduler liveness belongs to `/api/status` and ops diagnostics. | delegated goal | 2026-06-12 |
| Should News source status introspect runtime provider objects to learn supported provider types? | No. Supported News provider types are a static runtime contract; the route combines that contract with persisted source rows and source-quality reads. | delegated goal | 2026-06-12 |
| Should News worker/status provider contract validation introspect feed clients or private registries? | No. Supported News provider types are the static platform contract; feed clients fetch provider observations and do not expose capability discovery to runtime validation. | delegated goal | 2026-06-12 |
| Should News provider-contract validation fallback to Python provider-type enums when DB schema introspection is missing? | No. Schema provider types come from the live `news_sources` DB constraint; missing schema introspection must fail closed instead of guessing from code enums. | delegated goal | 2026-06-12 |
| Should News item-process admission use worker-memory fallbacks when repository context is incomplete? | No. Admission context must come from PostgreSQL repository readback after deterministic fact writes; missing context fails closed and retries instead of producing admission from in-memory compatibility data. | delegated goal | 2026-06-12 |
| Should News fetch synthesize dirty targets from `news_item_id` when canonical upsert omits `affected_news_item_ids`? | No. Canonical upsert/remap cleanup owns the affected item set; missing affected rows are a repository contract failure and must fail closed instead of enqueueing fallback dirty targets. | delegated goal | 2026-06-12 |
| Should News projection dirty enqueue accept raw item ids when `servable_news_item_ids` is missing? | No. Page/brief dirty targets must pass through the News repository servable filter; missing filter contract fails closed instead of enqueueing raw ids. | delegated goal | 2026-06-12 |
| Should Token Radar source-dirty enqueue/claim paths treat `token_radar_source_dirty_events` as optional? | No. Ingest, resolution reprocess, projection worker, and projection service must require the source-event dirty queue repository; missing contract fails closed instead of becoming an empty queue. | delegated goal | 2026-06-12 |
| Should notification aggregated external delivery reactivation fall back to insert-only delivery enqueue when `enqueue_or_requeue_delivery` is missing? | No. Reactivating failed/dead external deliveries is a required notification control-plane repository contract; missing requeue support must fail closed instead of silently preserving failed deliveries. | delegated goal | 2026-06-12 |
| Should Pulse low-information gating skip public-row hiding when `hide_public_candidate_for_low_information` is missing? | No. Low-information gating must hide stale public Pulse rows through the Pulse candidates repository; missing hide support must fail the dirty trigger for retry instead of marking it done. | delegated goal | 2026-06-12 |
| Should `/api/macro/modules/assets` treat a missing `latest_macro_daily_brief` repository method as an absent `assets_today` brief? | No. Missing rows may be absent read-model state, but missing repository read contract is a server-side contract failure and must fail closed. | delegated goal | 2026-06-12 |
| Should `/api/macro/modules/assets/crypto-derivatives` treat a missing `cex_oi_radar` repository as no CEX board? | No. Missing board rows are read-model state; missing repository contract is a server-side contract failure and must fail closed. | delegated goal | 2026-06-12 |
| Should Token Case or Search Inspect treat a missing `cex_detail_snapshots.latest_snapshot` repository method as no CEX detail? | No. Missing snapshot rows are product state; missing repository support is a backend read-contract failure and must fail closed. | delegated goal | 2026-06-12 |
| Should Token Case or Search Inspect treat a missing `latest_market_tick` repository method as `market_live.status = "missing"`? | No. Missing current tick rows are product state; missing repository support is a backend read-contract failure and must fail closed. | delegated goal | 2026-06-12 |
| Should Pulse dirty-trigger admission treat missing job/edge/capacity/queue-depth repository methods as empty control-plane state? | No. Missing Pulse control-plane repository support is a worker contract failure; the dirty trigger must fail/retry instead of being marked done or admitted from empty state. | delegated goal | 2026-06-12 |
| Should `macro import-bundle` fall back to raw `conn.transaction()` when a repository session omits `unit_of_work`? | No. Offline replay/seed still writes macro facts, import audit rows, and projection dirty targets, so missing session UoW or transaction guard support is a contract failure. | delegated goal | 2026-06-12 |
| Should `PulseCandidateJobService` fall back to `nullcontext` or raw `conn.transaction()` when a repository session omits `transaction`? | No. Pulse agent ledger, eval, candidate, playbook, admission, and job terminal writes must share `RepositorySession.transaction`; missing session transaction support fails before writes. | delegated goal | 2026-06-12 |
| Should News page/source-quality projection workers fall back to `nullcontext` or raw `conn.transaction()` when a repository session omits `transaction`? | No. News projection dirty claims, read-model writes, page dirty enqueue, and dirty target terminal state must share `RepositorySession.transaction`; missing session transaction support fails before claim/write. | delegated goal | 2026-06-12 |
| Should `PulseCandidateWorker` use raw `conn.transaction()` when a repository session omits `transaction`? | No. Pulse dirty-trigger claim, admission/edge/public visibility writes, job enqueue, and dirty target terminal updates must share `RepositorySession.transaction`; missing session transaction support fails before claim/write. | delegated goal | 2026-06-12 |
| Should News fetch/process/brief writer workers use raw `conn.transaction()` when a repository session omits `transaction`? | No. News provider observation/canonical item facts, deterministic item facts, agent admission/current brief state, run ledgers, projection dirty work, and claim/failure state must share `RepositorySession.transaction`; missing session transaction support fails before reconcile, claim, or write. | delegated goal | 2026-06-12 |
| Should Event Anchor stale cleanup fall back to manual commit when a worker session omits `unit_of_work`? | No. Stale job terminalization and matching enriched-event lifecycle writes must share worker-session `unit_of_work`; missing UoW support fails before cleanup writes. | delegated goal | 2026-06-12 |
| Should Token Capture Tier projection keep `commit=True`, manual commit probing, or dirty-target claim before the session transaction? | No. Dirty target claim, tier row writes/demotions, and dirty target done state must share `RepositorySession.transaction`; missing session transaction support fails before claim/write. | delegated goal | 2026-06-12 |
| Should Event Anchor repository terminal paths fall back to `nullcontext` when a connection omits `transaction`? | No. Event-anchor job terminalization and terminal-ledger writes must share the connection transaction; missing transaction support fails before writes. | delegated goal | 2026-06-12 |
| Should News projection dirty-target terminalization fall back to `nullcontext` when a connection omits `transaction`? | No. News projection claimed-row delete and terminal-ledger writes must share the connection transaction; missing transaction support fails before delete/ledger SQL. | delegated goal | 2026-06-12 |
| Should ops projection dirty repair `--execute` fall back to `nullcontext` when a connection omits `transaction`? | No. Dry-run may remain read-only without a transaction, but execute mode writes dirty targets and must fail before repair scans or queue writes when transaction support is missing. | delegated goal | 2026-06-12 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Read APIs are provider-free. | Architecture and unit tests reject `runtime.stock_quote_provider` in `/api/stocks-radar` and reject quote-provider calls from `StocksRadarService`. |
| Worker manifest matches runtime behavior. | Static and unit tests classify `resolution_refresh` as a dirty lookup queue consumer and reject old once helpers. |
| PostgreSQL stale-running cleanup is bounded. | Repository SQL tests and schema tests require partial index coverage plus `LIMIT` and `FOR UPDATE SKIP LOCKED` for stale terminalization. |
| Token Radar publish path is projection-only. | Unit tests prove `refresh_rank_set` does not call retention prune methods. |
| Pulse public reads avoid JSONB event-array expansion. | Static tests reject `jsonb_array_elements_text` from `pulse_read_repository.py`. |
| Signal Pulse public health is read-model state only. | Source and contract tests reject `_worker_running` and `agent_worker_running` in the Signal Pulse public path, schemas, OpenAPI, and frontend contracts. |
| News provider capability validation is provider-object and enum-fallback free. | Architecture and unit tests reject `runtime.providers`, `feed_client`, `_registry`, feed-client `supported_provider_types()` probing, and `PROVIDER_TYPES` schema fallback from `/api/news/sources/status`, News runtime status, and `NewsFetchWorker`; integration registry tests bind the runtime registry to the static platform provider-type contract. |
| News item-process admission reads persisted context. | Architecture and unit tests reject worker-memory `fallback_*` context from `NewsItemProcessWorker` and prove missing repository readback does not write agent admission. |
| News fetch dirty targets use canonical repository affected sets. | Architecture and unit tests reject `fallback_news_item_id` and prove missing `affected_news_item_ids` fails the fetch run without dirty target or wake emission. |
| News page/brief dirty enqueue requires repository servable filtering. | Architecture and unit tests reject `getattr`/raw-id fallback from `news_projection_work.py` and prove missing `servable_news_item_ids` fails without enqueue. |
| Token Radar source dirty queue is a required projection contract. | Architecture and unit tests reject optional `token_radar_source_dirty_events` fallbacks and prove missing source-dirty repositories fail closed instead of skipping enqueue/claim. |
| Notification external delivery requeue is a required control-plane contract. | Architecture and unit tests reject `enqueue_or_requeue_delivery` probing/fallback and prove aggregated external delivery reactivation fails closed when the repository contract is absent. |
| Pulse low-information hiding is a required read-model visibility contract. | Architecture and unit tests reject optional low-information hide fallback and prove missing hide support fails the dirty trigger instead of marking stale public rows done. |
| Pulse dirty-trigger control-plane reads are required repository contracts. | Architecture and unit tests reject optional job, edge, recent-failure, pending-count, and queue-depth fallbacks and prove missing job-state support fails the dirty trigger instead of marking it done. |
| Macro assets daily brief read is a required repository contract. | Architecture and unit tests reject optional `latest_macro_daily_brief` loader fallback and prove a missing repository method fails closed instead of returning a normal assets module. |
| Macro crypto-derivatives CEX board read is a required repository contract. | Architecture and unit tests reject optional `cex_oi_radar` repository fallback and prove missing repository support fails closed instead of returning a module without the board. |
| Token Case CEX detail read is a required repository contract. | Architecture and unit tests reject optional `cex_detail_snapshots.latest_snapshot` fallback and prove missing snapshot repository support fails closed for `CexToken` dossiers; Search Inspect passes the same repository into token-result dossiers. |
| Token Case market-live read is a required repository contract. | Architecture and unit tests reject optional `latest_market_tick` fallback and prove missing current-tick repository support fails closed instead of returning a normal dossier with `market_live.status = "missing"`. |
| Notification worker session Unit of Work is required. | Architecture and unit tests reject optional UoW/nullcontext/manual commit fallback and prove missing `unit_of_work` fails before notification facts or delivery rows are written. |
| Notification delivery session transaction is required. | Architecture and unit tests reject worker `.conn.commit()` / optional transaction fallback and prove missing `transaction` fails before delivery claim, while external push IO stays outside DB transactions. |
| Macrodata bundle import session transaction is required. | Architecture and unit tests reject optional UoW/raw `conn.transaction()`/optional `require_transaction` fallback and prove missing session contracts fail before macro facts or import runs are written. |
| Pulse candidate job service session transaction is required. | Architecture and unit tests reject `nullcontext`/raw `conn.transaction()` fallback and prove missing session transaction fails before Pulse agent/candidate/job writes. |
| News projection worker session transaction is required. | Architecture and unit tests reject `nullcontext`/raw `conn.transaction()` fallback and prove missing session transaction fails before page/source-quality dirty claims or read-model writes. |
| Pulse candidate worker session transaction is required. | Architecture and unit tests reject `_transaction(repos.conn)`/raw `conn.transaction()` fallback and prove missing session transaction fails before Pulse dirty-target claim or writes. |
| News runtime writer worker session transaction is required. | Architecture and unit tests reject raw `repos.conn.transaction()` fallback and prove missing session transaction fails before News source reconcile, item claim, or brief policy-skip writes. |
| Event Anchor stale cleanup worker-session Unit of Work is required. | Architecture and unit tests reject manual commit fallback and prove missing `unit_of_work` fails before stale job terminalization or enriched-event lifecycle writes. |
| Token Capture Tier projection session transaction is required. | Architecture and unit tests reject `commit=True`, `commit: bool`, `_commit_if_supported`, and manual `commit()` fallback, and prove missing session transaction fails before dirty target claim or tier writes. |
| Event Anchor repository terminal connection transaction is required. | Architecture and unit tests reject `nullcontext`/optional connection-transaction fallback and prove missing transaction fails before job terminal or terminal-ledger SQL. |
| Queue Terminal operator resolution connection transaction is required. | Architecture and unit tests reject `nullcontext`/manual commit fallback and prove missing transaction fails before `SELECT ... FOR UPDATE` or operator action writes. |
| Discovery lookup terminalization connection transaction is required. | Architecture and unit tests reject `nullcontext`/manual commit fallback and prove missing transaction fails before claimed lookup delete or terminal-ledger SQL. |
| News projection dirty-target terminalization connection transaction is required. | Architecture and unit tests reject `nullcontext`/manual commit fallback and prove missing transaction fails before claimed dirty-target delete or terminal-ledger SQL. |
| Ops projection dirty repair execute transaction is required. | Architecture and unit tests reject execute-mode `nullcontext` fallback and prove missing transaction fails before repair scans or dirty-target enqueue, while dry-run remains read-only. |
| Pulse job terminal/dead connection transaction is required. | Architecture and unit tests reject `nullcontext`/manual commit fallback and prove missing transaction fails before `pulse_agent_jobs` terminal/dead updates or terminal-ledger SQL. |
| Pulse admission connection transaction is required. | Architecture and unit tests reject shared `nullcontext`/raw transaction fallback and prove missing transaction fails before edge observation or budget SQL. |
| Token Profile Current dirty repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `token_profile_current_dirty_targets` queue SQL. |
| Token Image Source dirty repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `token_image_source_dirty_targets` queue SQL. |
| Asset Profile Refresh target repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `asset_profile_refresh_targets` queue SQL. |
| Asset Profile source-cache repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `asset_profiles` ready/status SQL, while worker service writes remain caller-owned inside `RepositorySession.transaction`. |
| Token Capture Tier dirty repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `token_capture_tier_dirty_targets` queue SQL. |
| Token Radar rank publication connection transaction is required. | Architecture and unit tests reject optional transaction probing and prove non-callable transaction support fails before current-row publication side effects. |
| Event Anchor repository transaction helper uses a direct connection contract. | Architecture and unit tests reject optional transaction probing and prove non-callable transaction support fails before terminal job or ledger side effects. |
| Account Quality backfill connection transaction is required. | Architecture and unit tests reject naked `self.repository.conn.commit()` fallback and prove missing transaction support fails before backfill reads or writes. |
| Asset Market sync service connection transaction is required. | Architecture and unit tests reject naked `*.conn.commit()` fallback, prove missing transaction support fails before registry/profile writes, and keep provider reads outside DB transactions. |
| CEX Token Profile source-cache repository connection transaction is required. | Architecture and unit tests reject manual `self.conn.commit()` fallback and prove missing transaction fails before `cex_token_profiles` SQL, while sync service writes remain caller-owned inside its connection transaction. |
| CLI ops execute connection transaction is required. | Architecture and unit tests reject `commit=True`, naked `.conn.commit()`, `nullcontext`, and optional transaction probing in `ops.py`, while keeping dry-run and provider iteration outside DB write transactions. |
| NotificationRepository repository-owned writes require connection transactions. | Architecture and unit tests reject naked `self.conn.commit()`, `nullcontext`, and optional transaction probing, prove missing transaction support fails before notification/read-marker/delivery SQL, and keep NotificationWorker writes caller-owned with `commit=False` inside worker-session `unit_of_work`. |
| SDD evidence tracks root-fix completion. | SDD validator, feature gate, targeted tests, and final `make check-all` evidence are captured in `verification.md`; until integration-heavy gates are allowed and pass, the feature remains active rather than verified. |

## First principles

PostgreSQL material facts and derived read models are the business truth; provider raw frames and request-time provider calls are inputs, not read-model substitutes. AGENTS.md:11 states that material facts are the only business truth and derived read models are rebuildable, while `docs/ARCHITECTURE.md:1` defines the system architecture boundary.

Each read model has a single runtime writer and unchanged projections write zero serving rows. AGENTS.md:11 captures the single-writer and stable-key invariant; `docs/WORKER_FLOW.md:1` is the worker flow contract this feature must keep aligned.

PostgreSQL queue and maintenance work must be bounded, index-backed, and friendly to concurrent workers. `docs/references/POSTGRES_PERFORMANCE.md:1` is the project reference for queue diagnostics and PostgreSQL performance.

Follow-up read-path review found that public WebSocket replay capped the
returned replay count but not the subscription filter cardinality, and token
filter replay called `recent_events(limit=replay, ...)` once per selected
symbol/address before per-event payload hydration. The target contract is that
`/ws` replay validates total filter values before mutating the client
subscription, returns `too_many_filters` for oversized subscriptions, caps
`replay` through a named constant, and divides token-filter replay limit across
the selected filters before PostgreSQL reads begin
(`src/parallax/app/surfaces/api/ws.py:17`,
`src/parallax/app/surfaces/api/ws.py:18`,
`src/parallax/app/surfaces/api/ws.py:114`,
`src/parallax/app/surfaces/api/ws.py:122`,
`src/parallax/app/surfaces/api/ws.py:136`,
`src/parallax/app/surfaces/api/ws.py:152`,
`src/parallax/app/surfaces/api/ws.py:157`,
`src/parallax/app/surfaces/api/ws.py:160`,
`src/parallax/app/surfaces/api/ws.py:221`,
`src/parallax/app/surfaces/api/ws.py:229`,
`src/parallax/app/surfaces/api/ws.py:239`,
`tests/unit/test_public_event_token_payloads.py:64`,
`tests/unit/test_public_event_token_payloads.py:90`).

Follow-up review found the next SQL performance layer in the same WebSocket
replay path: after replay events were selected, `_replay_events(...)` still
called the single-event `_payload_for_event(...)` for each replay item, which
meant replay pages hydrated projected entities, alerts, token intents, and
event-token resolutions through per-event repository reads. The target contract
is that WebSocket replay first selects and bounds the page event ids, then
hydrates public event payloads through page-level batch reads
(`src/parallax/app/surfaces/api/ws.py:162`,
`src/parallax/app/surfaces/api/ws.py:164`,
`src/parallax/app/surfaces/api/ws.py:165`,
`src/parallax/app/surfaces/api/ws.py:166`,
`src/parallax/app/surfaces/api/ws.py:214`,
`src/parallax/app/surfaces/api/ws.py:217`,
`src/parallax/app/surfaces/api/ws.py:218`,
`src/parallax/app/surfaces/api/ws.py:219`,
`src/parallax/app/surfaces/api/ws.py:220`,
`tests/unit/test_public_event_token_payloads.py:102`,
`tests/unit/test_public_event_token_payloads.py:115`,
`tests/unit/test_public_event_token_payloads.py:117`,
`tests/unit/test_public_event_token_payloads.py:119`,
`tests/unit/test_public_event_token_payloads.py:121`).

## Goals

- G1. `/api/stocks-radar` performs no provider IO and does not depend on `runtime.stock_quote_provider`.
- G2. `resolution_refresh` is documented and tested as a dirty lookup queue consumer, with no old once-helper compatibility path.
- G3. Notification stale-running terminalization is index-backed and bounded per claim call.
- G4. Token Radar rank publication does not run retention prune work in `refresh_rank_set`.
- G5. Pulse public read filtering no longer expands candidate JSONB event id arrays in SQL.
- G6. Signal Pulse public health does not expose scheduler or worker liveness as read-model state.
- G7. News source status and News provider-contract validation report provider capabilities from a static runtime contract and schema capabilities from the live DB constraint, not runtime provider objects or Python enum fallbacks.
- G8. SDD tasks and verification evidence prove each root fix through tests and final repository gates.
- G9. News item-process agent admission uses repository readback of persisted item/entity/mention/fact context and fails closed when that readback is missing.
- G10. News fetch page dirty targets come only from repository-returned `affected_news_item_ids` after canonical upsert/remap cleanup.
- G11. News page/brief dirty enqueue uses the repository `servable_news_item_ids` filter and fails closed when that filter contract is missing.
- G12. Notification aggregated external delivery reactivation uses the repository `enqueue_or_requeue_delivery` contract and does not fall back to insert-only delivery enqueue.
- G13. Pulse low-information gate uses the repository `hide_public_candidate_for_low_information` contract and fails dirty triggers when that contract is missing.
- G14. Macro assets daily brief uses the repository `latest_macro_daily_brief` contract and does not turn a missing method into an empty brief.
- G15. Macro crypto-derivatives CEX board uses the repository `cex_oi_radar.latest_board` contract and does not turn a missing repository into an omitted board.
- G16. Token Case and Search Inspect use the repository `cex_detail_snapshots.latest_snapshot` contract for `CexToken` dossiers and do not turn missing repository support into omitted CEX detail.
- G17. Token Case and Search Inspect use the repository `latest_market_tick` contract for market-live blocks and do not turn missing repository support into a missing market snapshot.
- G18. Pulse dirty-trigger admission uses required job, edge-state, recent-failure, pending-count, and queue-depth repository contracts and does not turn missing control-plane support into empty state.
- G19. Notification Rule writes notification facts and delivery control rows inside the worker-session `unit_of_work` and does not turn missing session UoW support into `nullcontext` plus manual commit.
- G20. Macrodata bundle import writes macro facts, import audit rows, and projection dirty targets inside `RepositorySession.unit_of_work` and does not turn missing session UoW or `require_transaction` support into raw connection transaction fallback.
- G21. PulseCandidateJobService writes Pulse agent run/step/eval/candidate/playbook/admission/job terminal rows inside `RepositorySession.transaction` and does not turn missing session transaction support into `nullcontext` or raw connection transaction fallback.
- G22. News page/source-quality projection workers claim dirty targets, write read models, enqueue downstream page dirty work, and mark dirty targets done/error inside `RepositorySession.transaction`, without turning missing session transaction support into `nullcontext` or raw connection transaction fallback.
- G23. PulseCandidateWorker claims dirty targets, writes admission/edge/public visibility/job enqueue state, and marks dirty targets done/error inside `RepositorySession.transaction`, without turning missing session transaction support into raw connection transaction fallback.
- G24. News fetch/process/brief writer workers write provider/canonical item facts, deterministic item facts, agent admission/current brief state, run ledgers, projection dirty work, and claim/failure state inside `RepositorySession.transaction`, without turning missing session transaction support into raw connection transaction fallback.
- G25. EventAnchorBackfillWorker stale cleanup terminalizes event-anchor job rows and matching enriched-event lifecycle state inside worker-session `unit_of_work`, without turning missing session UoW support into manual commit fallback.
- G26. TokenCaptureTierWorker claims dirty targets, writes tier rows/demotions, and marks dirty targets done inside `RepositorySession.transaction`, without turning missing session transaction support into manual commit or claim-before-transaction compatibility.
- G27. EventAnchorBackfillJobRepository terminal paths write event-anchor job terminal state and terminal ledger rows inside the connection transaction, without turning missing connection transaction support into `nullcontext` compatibility.
- G28. NewsProjectionDirtyTargetRepository terminal paths delete claimed News projection dirty-target rows and write terminal ledger rows inside the connection transaction, without turning missing connection transaction support into `nullcontext` or manual commit compatibility.
- G29. Ops projection dirty repair execute mode scans and enqueues News projection dirty targets inside the connection transaction, without turning missing connection transaction support into `nullcontext` compatibility; dry-run remains read-only.
- G30. PulseJobsRepository terminal/dead paths write `pulse_agent_jobs` state and terminal ledger rows inside the connection transaction, without turning missing connection transaction support into `nullcontext` or manual commit compatibility.
- G31. PulseAdmissionRepository claim path writes edge observation, suppression/admission state, and target/candidate run-budget rows inside the connection transaction, without turning missing connection transaction support into `nullcontext` compatibility.
- G32. MacroIntelRepository observation-series current refresh writes changed current rows and publication state inside the connection transaction, without turning missing connection transaction support into `nullcontext` compatibility.
- G33. PulseJobsRepository job/run mutations use the connection transaction when the repository owns the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G34. Pulse agent write repositories use the shared connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G35. PulseTriggerDirtyTargetRepository queue mutations use the shared connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G36. NewsProjectionDirtyTargetRepository ordinary queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G37. TokenRadarSourceDirtyEventRepository source-edge queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G38. TokenRadarDirtyTargetRepository target queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G39. MarketTickCurrentDirtyTargetRepository queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G40. TokenProfileCurrentDirtyTargetRepository queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G41. TokenImageSourceDirtyTargetRepository queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G42. AssetProfileRefreshTargetRepository queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G43. TokenCaptureTierDirtyTargetRepository queue mutations use the connection transaction when they own the commit, without turning missing transaction support into manual `self.conn.commit()` compatibility.
- G44. TokenRadarProjection rank publication uses a callable connection transaction for publication-side writes, without optional transaction probing or non-contract TypeError fallthrough.
- G45. EventAnchorBackfillJobRepository terminal transaction helper uses a direct callable connection transaction contract, without optional transaction probing.
- G46. WakeBus and WakeWaiter require callable wake-pool PostgreSQL commit/listen contracts for `NOTIFY`/`LISTEN`, without treating missing commit or `notifies` support as a successful silent wake fallback.
- G47. ResolutionRefreshWorker uses the formal repository-session transaction for lookup running, finish, fail, and claim-completion state transitions, without manual `repos.conn.commit()` or raw connection transaction compatibility.
- G48. NotificationDeliveryWorker uses the formal repository-session transaction for delivery claim, pre-flight fail, log complete, and external IO completion/failure state transitions, without worker `.conn.commit()` or repository-owned manual commit compatibility on the worker path.
- G49. Token intent rebuild and resolution reprocess entrypoints use the formal `RepositorySession.transaction` for token evidence, intent, lookup-key, resolution, discovery dirty lookup, identity evidence, and Token Radar source-dirty writes, and `TokenIntentResolver` exposes no direct commit flag or `resolutions.conn.commit()` compatibility.
- G50. MacroViewProjectionWorker claims `macro_projection_dirty_targets`, refreshes observation-series current rows, writes the current macro view snapshot, and marks dirty targets done inside `RepositorySession.transaction`; changed snapshots emit `macro_view_snapshot_updated` only after the transaction exits, without worker-owned `commit=True` fragments.
- G51. TokenRadarProjection dirty work processes claimed source/target dirty rows, rank-source edge updates, target-feature writes/deletes, rank publication attempts, and dirty done/error terminalization inside one explicit connection transaction, without treating `commit=False` on an autocommit connection as a delayed commit boundary.
- G52. AccountQualityBackfillService replays upstream facts into account profiles, token-call stats, and quality snapshots inside one callable connection transaction, without treating ops-only maintenance as permission to use naked `conn.commit()` compatibility.
- G53. Asset Market route/profile/symbol sync services keep provider reads outside DB transactions and write registry/profile rows inside one callable connection transaction, without naked `conn.commit()` compatibility.
- G54. CLI ops execute commands use callable connection transactions for repair/sync writes, keep dry-runs read-only, and do not retain `commit=True` or naked `.conn.commit()` compatibility.
- G55. Domain workers that receive an injected wake emitter/listener object call the required wake method directly after successful DB state changes, without silently treating a malformed object as an acceptable missed wake.
- G56. `WorkerBase` treats an injected `wake_waiter` as a concrete runtime contract for wake, wait, and close lifecycle methods instead of silently falling back to local sleep or skipped close when the object is malformed.
- G57. CEX Market Intel current/read-model writes require explicit repository-session or connection transactions for board rows, publication state, detail snapshots, derivative series, and attempt-state writes, without naked `self.conn.commit()` compatibility in repository-owned commit paths.
- G58. Narrative Admission dirty-target queue mutations require callable connection transactions when they own commits, without preserving naked `self.conn.commit()` compatibility on the active `narrative_admission` read-model control plane.
- G59. Narrative Admission serving-row mutations require callable connection transactions when `NarrativeRepository` owns commits for `narrative_admissions` upsert or stale-target delete, without optional commit probing compatibility.
- G60. Token Profile Current serving-row mutations require callable connection transactions when `TokenProfileCurrentRepository` owns commits for `token_profile_current` upsert, without naked `self.conn.commit()` compatibility.
- G61. Token Image Asset lifecycle mutations require callable connection transactions when `TokenImageAssetRepository` owns commits for `token_image_assets` pending/ready/error/unsupported writes, and worker terminal image writes must remain caller-owned inside `RepositorySession.transaction`.
- G62. Asset identity evidence/current mutations require callable connection transactions when `IdentityEvidenceRepository` owns commits for registry asset, identity evidence, or current identity writes, without naked `self.conn.commit()` compatibility.
- G63. Registry repository mutations require callable connection transactions when `RegistryRepository` owns commits for registry assets, CEX tokens, price feeds, or US equity symbol writes, without naked `self.conn.commit()` compatibility.
- G64. Discovery repository ordinary lookup queue/result mutations require callable connection transactions when `DiscoveryRepository` owns commits for enqueue, claim, done, reschedule, start, finish, or fail state transitions, without naked `self.conn.commit()` compatibility.
- G65. Asset Profile source-cache mutations require callable connection transactions when `AssetProfileRepository` owns commits for `asset_profiles` ready/status writes, while `asset_profile_refresh` worker profile writes remain caller-owned inside `RepositorySession.transaction`.
- G66. CEX Token Profile source-cache mutations require callable connection transactions when `CexTokenProfileRepository` owns commits for `cex_token_profiles` ready writes, while `sync_cex_token_profiles` writes remain caller-owned inside its service transaction.
- G67. Token fact repository-owned writes require callable connection transactions when token evidence, token intents/evidence links, lookup keys, or current intent resolutions own commits, while ingest/rebuild/reprocess paths remain caller-owned inside `unit_of_work` or `RepositorySession.transaction`.
- G68. Queue terminal retry transitions require explicit repository/session contracts for discovery lookup, event-anchor job, and Pulse agent job requeue paths, without optional `getattr(..., None)` repository or method probing.
- G69. Token Radar serving read-model repository-owned writes require callable connection transactions before current-row publication, target-feature cache mutation, first-seen updates, or publication failure state writes.
- G70. Evidence ingest repository-owned writes require callable connection transactions before raw-frame input observations or event-entity fact edges write SQL, while full event ingest keeps those writes caller-owned inside `EvidenceRepository.unit_of_work`.
- G71. ProjectionRepository control-plane mutations require callable connection transactions before projection offset, run ledger, or dirty-range queue SQL, while Token Radar rank publication keeps those writes caller-owned inside its explicit projection transaction.
- G72. TokenRadarRankSourceRepository rank-source edge mutations require callable connection transactions before repository-owned `token_radar_rank_source_events` population or prune SQL, while `TokenRadarRankSourceQuery` no longer owns commit behavior and projection keeps edge writes caller-owned inside its explicit transaction.
- G73. TokenFactorEvaluationRepository score-evaluation read-model mutations require callable connection transactions before repository-owned `token_score_evaluations` single or batch upsert SQL, and batch upsert must keep per-row writes caller-owned inside the repository transaction.
- G74. SignalRepository watched-account alert writes require callable connection transactions before repository-owned `account_token_alerts` insert SQL, while ingest keeps alert writes caller-owned inside `EvidenceRepository.unit_of_work`.
- G75. AccountQualityRepository read-model mutations require callable connection transactions before repository-owned `account_profiles`, `account_token_call_stats`, or `account_quality_snapshots` write SQL, while backfill and GMGN directory sync keep repository writes caller-owned inside their outer transaction.
- G76. NotificationRepository notification fact/read-marker writes and delivery enqueue/requeue mutations require callable connection transactions before repository-owned `notifications`, `notification_reads`, or `notification_deliveries` SQL, while NotificationWorker keeps insert/enqueue writes caller-owned with `commit=False` inside worker-session `unit_of_work`.
- G77. NewsRepository source/fetch/provider item/canonical item/deterministic item fact/agent brief/source-quality/page-row mutations require callable connection transactions before repository-owned SQL, while News workers keep those writes caller-owned with `commit=False` inside `RepositorySession.transaction`.
- G78. MacroIntelRepository projection dirty-target claim/done/error mutations require callable connection transactions before repository-owned `macro_projection_dirty_targets` SQL, while MacroViewProjectionWorker keeps those writes caller-owned with `commit=False` inside `RepositorySession.transaction`.
- G79. TokenRadarProjection downstream dirty-target fan-out uses formal repository-session attributes for Pulse trigger, Narrative Admission, Token Profile Current, and Token Capture Tier dirty queues, without optional `getattr(..., None)` probes or custom missing-repository compatibility branches.
- G80. PulseEvidenceBuilder sealed evidence packet construction uses formal evidence source repository methods for source events, enriched events, market facts, identity facts, and current discussion digest, without optional method probes or empty-evidence compatibility defaults.
- G81. SignalPulseService public freshness health uses the formal `PulseReadRepository.freshness_health(...)` read contract, without probing `repository.conn`, instantiating freshness services from the read service, or treating missing repository support as empty health.
- G82. MacroSyncService queue-state notes use the formal `MacroIntelRepository.macro_sync_queue_summary(...)` contract after due-window enqueue, without optional method probes or empty summary compatibility defaults.
- G83. Asset Market Binance CEX route sync dry-run/execute plan counts use the formal `RegistryRepository.binance_usdt_perp_sync_plan_counts(...)` contract, without optional method probes or input-size insert/delete estimates.
- G84. WorkerScheduler status/liveness decisions use direct worker `status_payload()` contracts, without optional hook probing, swallowed hook errors, non-object payload defaults, or fallback state inference from partial worker attributes.
- G85. API worker dependency helpers use the scheduler's canonical worker map and direct scheduler/worker `status_payload()` contracts for liveness and route-local worker access, without optional runtime field probes, swallowed hook errors, or ad-hoc worker unwrap aliases.
- G86. Collector `IngestService` construction uses formal `RepositorySession` repositories for token facts, discovery, market/enriched facts, event-anchor jobs, and Token Radar source-dirty fan-out, without optional bootstrap probes, constructor repository fallback, or unused target-dirty compatibility parameters.
- G87. WorkerScheduler unhealthy reason details use the same formal `status_payload()` data as liveness/startability, without direct worker attribute fallback for `last_error`, `unavailable_reason`, or `active_run_once_hard_timed_out_at_ms`.
- G88. Configured streaming providers expose `connection_state_payload()` as a formal runtime contract for stream worker degraded notes, readiness, ops diagnostics, and provider adapters, without optional hook probing or configured/disconnected fallbacks for missing state hooks.
- G89. Agent execution status surfaces use the formal `Runtime.agent_execution_gateway` root and direct `status_snapshot()` contract, without provider-bundle alias fallback or disabled-state fallback for malformed non-null gateways.
- G90. Runtime shutdown uses `DBPoolBundle.aclose()` as the formal pool lifecycle contract; `WorkerScheduler` must not close individual pool attributes as partial DB-bundle compatibility fallback.
- G91. Bootstrap failure cleanup uses the same `DBPoolBundle.aclose()` lifecycle contract after DB bundle creation, without startup-unwind fallback that closes individual pool attributes.
- G92. WakeBus emitters use the formal wake-pool connection context contract, without accepting a raw connection fallback from the connection factory.
- G93. WorkerBase single-writer advisory lock cleanup uses the formal advisory lock connection `release()` contract, without falling back to `close()` or optional release probing for malformed lock objects.
- G94. CLI ops one-shot worker commands use the same formal DB bundle and advisory lock lifecycle contracts as runtime workers, without closing individual pool attributes or accepting `close()`-only advisory lock handles.
- G95. Collector upstream clients expose `aclose()` as the formal lifecycle contract, and `CollectorService` closes owned upstream clients through that contract without accepting `close()` fallback or optional awaitable probing.
- G96. Bootstrap/runtime provider cleanup uses explicit root lifecycle contracts (`providers.aclose()`, runtime `agent_execution_gateway.aclose()`, and `llm_gateway.aclose()`), without recursively scanning provider dataclasses, mappings, object slots, or `close/aclose`-shaped aliases.
- G97. Worker-owned provider cleanup uses each provider protocol's formal lifecycle method directly: Pulse candidate decision providers require `aclose()`, and News fetch source providers require synchronous `close()`, without cross-shape fallback or awaitable probing.
- G98. Provider wiring wrapper and partial-cleanup paths use formal synchronous provider `close()` contracts directly, without optional `getattr(..., "close", None)` probes that let malformed partial providers pass silently.
- G99. DB pool bundle creation failure cleanup uses formal synchronous pool `close()` contracts directly and records missing or failed partial-pool cleanup on the original startup exception instead of optional pool-close probing or masking the create failure.
- G100. DB pool discarded-connection cleanup uses the psycopg pool contract directly by closing the connection and returning it through `putconn`, without private `pool.close_returns(...)` compatibility or optional `conn.close` probing.
- G101. Market tick stream iterator cleanup uses a formal async iterator `aclose()` contract directly, without optional `getattr(iterator, "aclose", None)` probing that treats malformed stream iterators as successful no-close streams.
- G102. DBPoolBundle runtime pool shutdown uses the formal synchronous psycopg pool `close() -> None` contract directly, without accepting awaitable or non-None close results as compatibility shapes.
- G103. CLI ops asset-market one-shot commands close wired provider bundles through the formal `AssetMarketProviders.aclose()` root, without enumerating provider fields or optional `close()` probing as a second lifecycle path.
- G104. WorkerBase injected wake-waiter shutdown uses the formal synchronous `close() -> None` contract directly, without accepting awaitable or non-None close results as compatibility shapes.
- G105. WorkerScheduler runtime shutdown awaits formal async worker and DB lifecycle hooks directly, without `_maybe_await(...)` or `inspect.isawaitable(...)` accepting synchronous hook results as compatibility shapes.
- G106. LivePriceGateway fan-out uses the formal async WebSocket hub publish contract directly, without accepting synchronous callback results through `inspect.isawaitable(...)` as a test or runtime compatibility shape.
- G107. GMGN direct upstream WebSocket frame delivery uses the collector's formal async `handle_frame(...)` contract directly, without accepting synchronous callback results through `inspect.isawaitable(...)` as a test or runtime compatibility shape.
- G108. Agent execution capacity reservation release uses the formal synchronous resource-release contract directly, without accepting awaitable release results as alternate lifecycle shapes.
- G109. OpenNews REST ingestion uses the formal async HTTP poster contract directly, without accepting synchronous poster results through `inspect.isawaitable(...)` as a test or runtime compatibility shape.
- G110. PostgreSQL health checks use the formal connection `commit()` and `rollback()` contracts directly, without `hasattr(...)` probes that silently accept fake or malformed connections missing transaction cleanup methods.
- G111. OpenNews synchronous worker bridge accepts a formal coroutine object and closes it directly when called from an active event loop, without optional `getattr(coro, "close", None)` probing or `Any`-typed awaitable compatibility.
- G112. PostgreSQL transaction guards read the formal psycopg `conn.info.transaction_status` contract directly, without accepting fake connections that omit transaction-status evidence.
- G113. Enabled Asset Market provider-IO workers surface missing provider dependencies as `unavailable`, not `disabled`, so readiness and ops status distinguish operator-disabled workers from broken runtime wiring.
- G114. Worker factories read formal `WiredProviders` domain bundle roots directly, without optional `getattr(ctx.providers, ..., None)` probes that turn malformed composition roots into empty provider sets.
- G115. Runtime status surfaces read formal `Runtime.providers` domain bundle roots directly, without optional `getattr(runtime, "providers", None)` probes that turn malformed composition roots into disabled provider inventory.
- G116. Ops diagnostics reads the formal collector status contract directly, without optional collector/status/to_dict probes that turn malformed collector wiring into an empty details object.
- G117. Ops diagnostics reads the formal Asset Market provider-health bundle contract directly, without optional `provider_health` probes that turn malformed provider-bundle wiring into an empty provider inventory.
- G118. Asset Market worker factories read formal provider-bundle fields directly, without optional field probes that turn malformed bundle shapes into ordinary unavailable provider workers.
- G119. LivePriceGateway construction and fan-out bounds use the formal `settings.workers.live_price_gateway` object directly, without synthesizing worker settings, accepting provider bundles, or keeping target/TTL defaults in runtime code.
- G120. NewsPageProjectionWorker uses formal worker settings for SQL timeout, dirty-target claim batch, lease, and retry cadence, without runtime fallback defaults.
- G119. CEX Market Intel and News Intel worker factories read formal provider-bundle fields directly, without optional field probes that turn malformed bundle shapes into ordinary unavailable provider workers.
- G120. Runtime News provider-contract status reads formal News Intel settings directly, without optional settings probes that turn malformed runtime configuration into an empty configured-source set.
- G121. Ops diagnostics config/watchlist status reads formal runtime settings directly, without optional settings probes that turn malformed runtime configuration into empty config or idle watchlist state.
- G122. Ops diagnostics queue summaries read the formal runtime API pool connection contract directly, without optional DB/pool/connection probes that turn malformed runtime DB wiring into an empty queue list.
- G123. Worker queue-health enrichment reads the formal runtime API pool connection contract directly, without optional DB/pool/connection probes or `missing_connection` compatibility that turn malformed runtime DB wiring into ordinary unavailable queue state.
- G124. Runtime readiness keeps no unused notification-summary fallback helper that can swallow repository contract failures as an empty notifications object.
- G125. Worker factory missing-worker sentinels read formal worker settings blocks directly, without default-enabled or synthetic settings compatibility when `settings.workers.<name>` is absent.
- G126. `DBPoolBundle` wake-listener sizing reads the formal `settings.workers` contract and manifest-declared wake worker settings directly, without turning missing worker settings shape into zero wake listener demand.
- G127. CLI ops one-shot worker commands read the formal worker settings block directly for statement timeouts and advisory lock keys, without synthesizing `SimpleNamespace()` defaults when `settings.workers.<name>` is absent.
- G128. CLI ops one-shot advisory lock acquisition reads the worker's formal `_advisory_lock_key()` method directly, without accepting a bare `SINGLE_WRITER_KEY` attribute fallback as an alternate lock-key contract.
- G129. Repository/query code has no upward-import allowlist for deterministic service modules; shared leaf primitives used by repositories live under domain `types`.

Follow-up review found the same optional-runtime root in collector ingest wiring: `_ingest_service_for_repos(...)` accepted missing core repository-session fields through `getattr(..., None)`, while `IngestService.__init__(...)` recreated repositories from `evidence.conn` and kept a stale `token_radar_dirty_targets` constructor parameter (`docs/reviews/kappa-cqrs-root-cause-analysis-zh-2026-06-12.md`). The target contract is that ingest receives the formal session shape and fails before fact/control writes when token fact, discovery, market/enriched, event-anchor, or source-dirty repositories are missing (`docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `src/parallax/app/runtime/repository_session.py`, `src/parallax/app/runtime/bootstrap.py`, `src/parallax/domains/evidence/services/ingest_service.py`).

Follow-up review found the same status-control root inside `unhealthy_reasons()`: reason details now must use the single `status_payload()` source of truth for `last_error`, `unavailable_reason`, and `active_run_once_hard_timed_out_at_ms`, because stale worker attributes can otherwise override payload errors or hide hard timeouts (`src/parallax/app/runtime/worker_scheduler.py:89`, `src/parallax/app/runtime/worker_scheduler.py:92`, `src/parallax/app/runtime/worker_scheduler.py:162`, `src/parallax/app/runtime/worker_scheduler.py:169`, `src/parallax/app/runtime/worker_scheduler.py:192`, `tests/unit/test_worker_scheduler.py:391`, `tests/architecture/test_worker_runtime_contracts.py:292`).

Follow-up review found the same optional-runtime root in stream provider state wiring: `DexMarketStreamProvider` and `UpstreamClientProtocol` now declare `connection_state_payload()` (`src/parallax/domains/asset_market/providers.py:163`, `src/parallax/domains/ingestion/providers.py:24`), and the stream worker, readiness, ops diagnostics, and OKX adapter call it directly instead of optional `getattr(..., None)` probing (`src/parallax/domains/asset_market/runtime/market_tick_stream_worker.py:238`, `src/parallax/app/runtime/app.py:311`, `src/parallax/app/runtime/ops_diagnostics.py:297`, `src/parallax/app/runtime/provider_wiring/okx.py:129`). Missing hooks are failed provider state, guarded by `tests/unit/test_market_tick_stream_worker.py:326` and `tests/architecture/test_worker_runtime_contracts.py:318`.

Follow-up review found the same optional-runtime root in agent execution status wiring: `/api/status` and ops diagnostics now read `runtime.agent_execution_gateway` directly and call `status_snapshot()` as a formal runtime contract (`src/parallax/app/runtime/app.py:207`, `src/parallax/app/runtime/ops_diagnostics.py:627`). A missing provider-bundle alias is no longer consulted, and a non-null gateway without `status_snapshot()` is unavailable runtime wiring, guarded by `tests/unit/test_ops_diagnostics.py:253`, `tests/unit/test_ops_diagnostics.py:266`, and `tests/architecture/test_worker_runtime_contracts.py:416`.

Follow-up review found the same optional-runtime root in DB pool shutdown: `WorkerScheduler` probed `db.aclose()` and then fell back to closing individual `api_pool`, `worker_pool`, `lock_pool`, `tool_pool`, and `wake_pool` attributes, while `DBPoolBundle` had no formal close root. The target contract is that `DBPoolBundle.aclose()` owns individual pool close order/error aggregation and `WorkerScheduler.stop()` calls `self.db.aclose()` directly, guarded by `tests/unit/test_db_pool_bundle.py`, `tests/unit/test_worker_scheduler.py`, and `tests/architecture/test_worker_runtime_contracts.py`.

Follow-up review found the same DB lifecycle split in bootstrap failure cleanup: after `DBPoolBundle.create(...)`, provider wiring or runtime assembly failure still unwound by closing `db.api_pool`, `db.worker_pool`, `db.lock_pool`, `db.tool_pool`, and `db.wake_pool` individually. The target contract is that startup unwind calls `db.aclose()` through a sync bridge, records cleanup failure on the original startup exception, and never duplicates pool-role ownership in `bootstrap.py`, guarded by `tests/unit/test_bootstrap_worker_runtime_wiring.py` and `tests/architecture/test_worker_runtime_contracts.py`.

Follow-up review found the same optional-runtime shape in wake emission: `WakeBus._notify(...)` probes `hasattr(conn_or_context, "__enter__")` and falls back to executing `pg_notify` on a raw connection when the factory does not return a context manager. The formal runtime path is `DBPoolBundle.wake_emitter()` over `wake_pool.connection`; a malformed connection factory is runtime wiring failure, not a supported raw-connection compatibility lane. The target contract is that WakeBus enters the wake-pool context directly, commits the checked-out connection, and fails before `pg_notify` when the factory omits the context protocol.

Follow-up review found the same explicit query-boundary gap in Pulse timeline context construction:
`build_pulse_timeline_context(...)` now requires caller-provided `window` and
`scope`, resolves active windows through `_window_ms(...)` / `WINDOW_MS[window]`,
uses the requested window's computed summary directly, and rejects unknown scopes
instead of restoring malformed inputs to `1h` or `all`
(`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:37`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:38`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:46`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:87`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:94`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:96`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:98`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:101`,
`src/parallax/domains/pulse_lab/services/pulse_timeline_context.py:106`,
`tests/architecture/test_pulse_no_compat.py:539`).

Follow-up review found the same scope fallback one layer up in the shared API
validator: `_scope(...)` used to rewrite any unknown value to `matched`. The
target contract is that API route defaults own public defaults, while `_scope`
accepts only `all`/`matched` and raises `ApiBadRequest("invalid_scope",
field="scope")` before read services or repositories run
(`src/parallax/app/surfaces/api/validators.py:31`,
`src/parallax/app/surfaces/api/validators.py:32`,
`src/parallax/app/surfaces/api/validators.py:34`,
`tests/unit/test_api_signal_pulse_contract.py:126`,
`tests/unit/test_api_signal_pulse_contract.py:138`,
`tests/architecture/test_api_read_paths_provider_free.py:72`,
`tests/architecture/test_api_read_paths_provider_free.py:75`,
`tests/architecture/test_api_read_paths_provider_free.py:80`).

Follow-up review found the same hidden window recovery in the ops
token-capture-tier rank-set repair helper: the parser already restricts
`--window`, but `_enqueue_token_capture_tier_rank_set(...)` still converted
malformed direct-call windows to a `24h` repair scan through
`WINDOW_MS.get(parsed_window, WINDOW_MS["24h"])`. The target contract is that
ops repair windows resolve through `WINDOW_MS[window]` and malformed helper
inputs fail before dry-run reads or execute-mode queue writes
(`src/parallax/app/surfaces/cli/commands/ops.py:499`,
`src/parallax/app/surfaces/cli/commands/ops.py:551`,
`src/parallax/app/surfaces/cli/commands/ops.py:553`,
`src/parallax/app/surfaces/cli/commands/ops.py:555`,
`tests/unit/test_ops_backfill_commands.py:483`,
`tests/unit/test_ops_backfill_commands.py:486`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:830`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:841`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:844`).

## Non-goals

- N1. Do not add a new US equity quote worker, table, or provider lane in this feature.
- N2. Do not preserve request-time quote compatibility behind a feature flag or fallback.
- N3. Do not rewrite all workers or redesign the full CQRS model.
- N4. Do not tune unrelated JSONB queries outside the Pulse public read path named here.
- N5. Do not replace Signal Pulse worker liveness with another public runtime-status field in the product read payload.
- N6. Do not add a second dynamic provider-capability discovery path or schema enum fallback for News source status, News fetch, or runtime status.
- N7. Do not preserve worker-memory fallback context for News item-process agent admission.
- N8. Do not infer News fetch dirty targets from the current representative `news_item_id` when repository affected-set evidence is missing.
- N9. Do not enqueue News page or brief dirty targets from raw ids when the repository servable filter is absent.
- N10. Do not preserve insert-only notification delivery enqueue as a compatibility fallback for failed/dead external delivery reactivation.
- N11. Do not preserve public Pulse rows by treating missing low-information hide support as a no-op.
- N12. Do not preserve optional Macro daily-brief loader behavior that treats missing repository methods as absent read-model rows.
- N13. Do not preserve optional Macro CEX board repository behavior that treats missing repositories as absent board data.
- N14. Do not preserve optional Token Case CEX detail behavior that treats missing snapshot repositories or methods as absent CEX detail.
- N15. Do not preserve optional Token Case market-live behavior that treats missing latest-market-tick repositories or methods as absent market data.
- N16. Do not preserve optional Pulse dirty-trigger state/capacity/queue-depth behavior that treats missing repository methods as no job, no edge, zero failures, zero pending jobs, or an empty queue.
- N17. Do not preserve optional Notification worker transaction behavior that treats a missing worker-session `unit_of_work` as permission to write under `nullcontext` and manually commit a repository connection.
- N18. Do not preserve optional Macrodata bundle import transaction behavior that treats missing `RepositorySession.unit_of_work` or `require_transaction` as permission to use raw `conn.transaction()`.
- N19. Do not preserve optional Pulse candidate job service transaction behavior that treats missing `RepositorySession.transaction` as permission to write under `nullcontext` or raw `conn.transaction()`.
- N20. Do not preserve optional News projection worker transaction behavior that treats missing `RepositorySession.transaction` as permission to claim dirty targets or write read-model/control rows under `nullcontext` or raw `conn.transaction()`.
- N21. Do not preserve Pulse candidate worker transaction behavior that treats missing `RepositorySession.transaction` as permission to claim dirty targets or write control/read-model rows under raw `conn.transaction()`.
- N22. Do not preserve News fetch/process/brief worker transaction behavior that treats missing `RepositorySession.transaction` as permission to reconcile, claim, or write under raw `conn.transaction()`.
- N23. Do not preserve Event Anchor stale cleanup transaction behavior that treats missing worker-session `unit_of_work` as permission to terminalize stale jobs or enriched-event lifecycle state under manual `commit()`.
- N24. Do not preserve Token Capture Tier projection transaction behavior that treats missing `RepositorySession.transaction` as permission to claim `token_capture_tier_dirty_targets`, write `token_capture_tier`, or mark dirty targets done under manual `commit()` compatibility.
- N25. Do not preserve Event Anchor repository terminal transaction behavior that treats missing connection `transaction` as permission to write `event_anchor_backfill_jobs` or terminal ledger rows under `nullcontext`.
- N26. Do not preserve Queue Terminal operator resolution behavior that treats missing connection `transaction` as permission to run `SELECT ... FOR UPDATE`, update `worker_queue_terminal_events.operator_action`, or retry work under `nullcontext` / manual commit compatibility.
- N27. Do not preserve Discovery terminal lookup behavior that treats missing connection `transaction` as permission to delete `token_discovery_dirty_lookup_keys` claims or write terminal ledger rows under `nullcontext` / manual commit compatibility.
- N28. Do not preserve News projection dirty-target terminal behavior that treats missing connection `transaction` as permission to delete `news_projection_dirty_targets` claims or write terminal ledger rows under `nullcontext` / manual commit compatibility.
- N29. Do not preserve ops projection dirty repair execute behavior that treats missing connection `transaction` as permission to scan News facts or enqueue `news_projection_dirty_targets` under `nullcontext`; only dry-run remains read-only without a transaction.
- N30. Do not preserve Pulse job terminal/dead behavior that treats missing connection `transaction` as permission to update `pulse_agent_jobs` or write terminal ledger rows under `nullcontext` / manual commit compatibility.
- N31. Do not preserve Pulse admission behavior that treats missing connection `transaction` as permission to update edge state or budget rows under `nullcontext`.
- N32. Do not preserve Macro observation-series refresh behavior that treats missing connection `transaction` as permission to delete/insert `macro_observation_series_rows` or update publication state under `nullcontext`.
- N33. Do not preserve PulseJobsRepository job/run mutation behavior that treats missing connection `transaction` as permission to enqueue, mark success, release running jobs, or clean stale runs through manual `self.conn.commit()`.
- N34. Do not preserve Pulse agent run/eval/evidence/candidate/playbook/admission mutation behavior that treats missing connection `transaction` as permission to write agent audit, packet, public candidate, playbook, edge, or budget rows through manual `self.conn.commit()`.
- N35. Do not preserve Pulse trigger dirty-target queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, retry, or reschedule queue rows through manual `self.conn.commit()`.
- N36. Do not preserve News projection dirty-target queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, or retry queue rows through manual `self.conn.commit()`.
- N37. Do not preserve Token Radar source dirty event queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, or retry source-edge queue rows through manual `self.conn.commit()`.
- N38. Do not preserve Token Radar target dirty queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, retry, or catch up target queue rows through manual `self.conn.commit()`.
- N39. Do not preserve Market Tick Current dirty queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, or retry current-market queue rows through manual `self.conn.commit()`.
- N40. Do not preserve Token Profile Current dirty queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, or retry profile-current queue rows through manual `self.conn.commit()`.
- N41. Do not preserve Token Image Source dirty queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, delete, or retry image-source queue rows through manual `self.conn.commit()`.
- N42. Do not preserve Asset Profile Refresh target queue mutation behavior that treats missing connection `transaction` as permission to enqueue, claim, reschedule, or retry provider-profile refresh queue rows through manual `self.conn.commit()`.
- N43. Do not preserve Token Capture Tier dirty queue mutation behavior that treats missing connection `transaction` as permission to enqueue rank-set work, claim, or delete done queue rows through manual `self.conn.commit()`.
- N44. Do not preserve Token Radar rank publication transaction behavior that treats optional transaction probing or Python `TypeError` from non-callable `transaction` attributes as an acceptable contract boundary.
- N45. Do not preserve Event Anchor terminal transaction helper behavior that treats optional transaction probing as an acceptable shape for job terminal or terminal-ledger writes.
- N46. Do not preserve wake bus/listener behavior that treats missing wake connection `commit` or listener `notifies` support as an acceptable local-wait or no-commit fallback.
- N47. Do not preserve ResolutionRefreshWorker behavior that treats direct `repos.conn.commit()`, raw `repos.conn.transaction()`, or optional session transaction probing as an acceptable boundary for lookup state-machine writes.
- N48. Do not preserve NotificationDeliveryWorker behavior that treats worker `.conn.commit()`, repository-owned delivery commit, or optional session transaction probing as an acceptable boundary for delivery state-machine writes.
- N49. Do not preserve token intent rebuild or token resolution reprocess behavior that treats direct `repos.conn.commit()` as an acceptable commit boundary for fact rebuild, lookup-key replacement, discovery enqueue, or Token Radar source-dirty enqueue.
- N50. Do not preserve MacroViewProjectionWorker behavior that commits dirty-target claim, series refresh, snapshot insert, and dirty-target done/error as separate worker-owned fragments or emits `macro_view_snapshot_updated` from inside the projection transaction.
- N51. Do not preserve TokenRadarProjection dirty-processing behavior that runs source-edge writes, target-feature writes/deletes, rank publication attempts, or dirty done/error terminalization outside one explicit connection transaction after dirty work is claimed.
- N52. Do not preserve Account Quality backfill behavior that relies on naked `conn.commit()` after `commit=False` repository calls, or treats missing connection transaction support as acceptable for ops-only read-model maintenance.
- N53. Do not preserve Asset Market sync behavior that writes CEX routes/profiles or US equity symbols through service-owned naked `conn.commit()`, or that holds provider reads inside DB transactions.
- N54. Do not preserve CLI ops execute behavior that writes dirty queues, News repair state, or GMGN directory rows through `commit=True`, naked `.conn.commit()`, `nullcontext`, or optional transaction probing.
- N55. Do not preserve worker wake-emitter behavior that probes `notify_*` / `wake()` with optional `getattr(..., None)` and silently drops a wake when a malformed object was injected.
- N56. Do not preserve `WorkerBase` compatibility that probes injected `wake_waiter` objects with optional `getattr(..., None)` / `hasattr(...)` and falls back to local wait or skipped close when the waiter contract is malformed.
- N57. Do not preserve CEX Market Intel read-model repository behavior that owns commits through `self.conn.commit()` or lets worker empty/failure paths publish attempt state outside `RepositorySession.transaction`.
- N58. Do not preserve Narrative Admission dirty-target repository behavior that owns enqueue/claim/done/error/reschedule commits through naked `self.conn.commit()` or optional transaction fallbacks.
- N59. Do not preserve NarrativeRepository admission write behavior that owns `narrative_admissions` upsert or stale-target delete commits through `_commit_if_available`, optional commit probing, or naked `self.conn.commit()`.
- N60. Do not preserve TokenProfileCurrentRepository current-row write behavior that owns `token_profile_current` upsert commits through naked `self.conn.commit()` or optional transaction fallbacks.
- N61. Do not preserve TokenImageAssetRepository lifecycle write behavior that owns `token_image_assets` pending/ready/error/unsupported commits through naked `self.conn.commit()`, and do not let the TokenImageMirror worker adapter publish terminal image state outside `RepositorySession.transaction`.
- N62. Do not preserve IdentityEvidenceRepository write behavior that owns `registry_assets`, `asset_identity_evidence`, or `asset_identity_current` commits through naked `self.conn.commit()` or optional transaction fallbacks.
- N63. Do not preserve RegistryRepository write behavior that owns `registry_assets`, `cex_tokens`, `price_feeds`, or `us_equity_symbols` commits through naked `self.conn.commit()` or optional transaction fallbacks.
- N64. Do not preserve DiscoveryRepository ordinary lookup queue/result behavior that owns `token_discovery_dirty_lookup_keys` or `token_discovery_results` commits through naked `self.conn.commit()` or optional transaction fallbacks.
- N65. Do not preserve AssetProfileRepository source-cache write behavior that owns `asset_profiles` ready/status commits through naked `self.conn.commit()` or optional transaction fallbacks, and do not let `asset_profile_refresh` worker writes open an inner repository-owned commit.
- N66. Do not preserve CexTokenProfileRepository source-cache write behavior that owns `cex_token_profiles` ready commits through naked `self.conn.commit()` or optional transaction fallbacks, and do not let `sync_cex_token_profiles` writes open an inner repository-owned commit.
- N67. Do not preserve TokenEvidenceRepository, TokenIntentRepository, TokenIntentLookupRepository, or IntentResolutionRepository behavior that owns token fact commits through naked `self.conn.commit()` or optional transaction fallbacks, and do not allow `insert_resolution` to take `pg_advisory_xact_lock` before a real connection transaction exists.
- N68. Do not preserve Queue Ops retry-transition behavior that treats missing `signals.conn`, `discovery.enqueue_lookup_keys`, `event_anchor_jobs.retry_terminal_job_from_snapshot`, or `pulse_jobs.retry_terminal_job_from_snapshot` as optional repository shape compatible with terminal retry handling.
- N69. Do not preserve TokenRadarRepository behavior that owns `token_radar_current_rows`, `token_radar_publication_state`, `token_radar_target_features`, or `token_radar_target_first_seen` commits through naked `self.conn.commit()` or takes publication advisory transaction locks before a real connection transaction exists.
- N70. Do not preserve EvidenceRepository or EntityRepository behavior that owns `raw_frames` or `event_entities` commits through naked `self.conn.commit()` or writes those input/fact rows before a real connection transaction exists.
- N71. Do not preserve ProjectionRepository behavior that owns `projection_offsets`, `projection_runs`, or `projection_dirty_ranges` commits through naked `self.conn.commit()` or claims dirty ranges before a real connection transaction exists.
- N72. Do not preserve `TokenRadarRankSourceQuery` commit behavior or `TokenRadarRankSourceRepository` delegation that can populate/prune `token_radar_rank_source_events` through naked `self.conn.commit()` instead of a repository-owned connection transaction.
- N73. Do not preserve TokenFactorEvaluationRepository behavior that owns `token_score_evaluations` commits through naked `self.conn.commit()` or lets single-score upserts execute before a real connection transaction exists.
- N74. Do not preserve SignalRepository behavior that owns `account_token_alerts` commits through naked `self.conn.commit()` or lets watched-account alert inserts execute before a real connection transaction exists.
- N75. Do not preserve AccountQualityRepository behavior that owns account-quality table commits through naked `self.conn.commit()` or lets profile/stat/snapshot writes execute before a real connection transaction exists.
- N76. Do not preserve NotificationRepository behavior that owns notification fact, read-marker, delivery enqueue, or failed/dead delivery requeue commits through naked `self.conn.commit()` or lets those writes execute before a real connection transaction exists.
- N77. Do not preserve NewsRepository behavior that owns News fact, deterministic processing, agent brief, source-quality, or page-row commits through naked `self.conn.commit()` or method-local transaction fallbacks instead of one repository transaction wrapper.
- N78. Do not preserve MacroIntelRepository dirty-target claim/done/error behavior that owns `macro_projection_dirty_targets` commits through naked `self.conn.commit()` or lets claim/done/error SQL execute before a real connection transaction exists.
- N79. Do not preserve TokenRadarProjection downstream dirty-target fan-out behavior that probes Pulse, Narrative Admission, Token Profile Current, or Token Capture Tier dirty repositories as optional attributes.
- N80. Do not preserve PulseEvidenceBuilder source repository behavior that treats missing evidence source methods as empty events, empty market/identity facts, or absent discussion digest.
- N81. Do not preserve SignalPulseService freshness-health behavior that probes a read repository's private `conn` attribute, bypasses the formal read repository method, or returns empty health when the repository contract is missing.
- N82. Do not preserve MacroSyncService queue-summary behavior that probes `macro_sync_queue_summary` as optional or returns `{}` when the repository/session contract is missing.
- N83. Do not preserve Asset Market route sync behavior that estimates Binance CEX token or price-feed plan counts from provider input length when `RegistryRepository.binance_usdt_perp_sync_plan_counts(...)` is missing.
- N84. Do not preserve repository/query upward-import allowlist entries that let persistence code depend on same-domain deterministic service modules for value objects, fingerprints, or payload hash primitives.

## Target architecture

After this change, `/api/stocks-radar` is a DB-only social attention endpoint over current `MarketInstrument` read facts. It returns quote metadata only as an explicit unavailable read-model state until a separate persisted quote projection exists. `resolution_refresh` is a dirty target worker whose manifest, tests, docs, and runtime all point at the same `token_discovery_dirty_lookup_keys` control-plane queue. Notification and Token Radar cleanup are bounded maintenance concerns rather than hidden table-wide work inside serving or publication paths. Notification Rule writes `notifications` facts and `notification_deliveries` control rows inside the worker-session `unit_of_work`; missing UoW support is a session contract failure, not a manual commit path. EventAnchorBackfillWorker stale cleanup terminalizes `event_anchor_backfill_jobs` and matching `enriched_events` lifecycle state inside the worker-session `unit_of_work`; missing UoW support is a session contract failure before cleanup writes, not a manual commit path. Macro import-bundle offline replay writes macro facts, import audit rows, and projection dirty targets inside `RepositorySession.unit_of_work`; missing UoW or `require_transaction` support is a session contract failure, not a raw connection transaction path. Pulse agent job execution writes agent ledger, deterministic eval, candidate, playbook, admission, and job terminal rows inside `RepositorySession.transaction`; missing session transaction support is a session contract failure, not a `nullcontext` or raw connection transaction path. PulseCandidateWorker dirty-trigger claim, admission/edge/public visibility writes, job enqueue, and dirty-target done/error updates also run inside `RepositorySession.transaction`; missing session transaction support is a session contract failure before claim/write, not a raw connection transaction path. News page/source-quality projection workers claim dirty targets, write `news_page_rows` / `news_source_quality_rows`, enqueue downstream page dirty work, and mark dirty targets done/error inside `RepositorySession.transaction`; missing session transaction support is a session contract failure before claim/write, not a `nullcontext` or raw connection transaction path. Notification external delivery reactivation uses the explicit `enqueue_or_requeue_delivery` repository contract for aggregated high-signal notifications and fails closed when that contract is missing. Pulse handle filtering no longer depends on expanding event id JSONB arrays in the public read query, and low-information gating must write the hidden public-row state through the Pulse candidates repository instead of silently skipping stale-row hiding. Pulse dirty-trigger admission and capacity checks read existing jobs, edge state, recent-failure counts, pending job counts, and queue depth only through the formal Pulse repositories; missing support fails the dirty trigger for retry instead of creating an empty control-plane view. Signal Pulse health is derived from persisted candidate summaries and freshness queries; runtime worker liveness is reported through status/ops surfaces, not the product read payload. Macro assets daily brief reads `assets_today` only through `repos.macro_intel.latest_macro_daily_brief(...)`; a missing row may be absent daily-brief state, but a missing repository method is a route/repository contract failure. Macro crypto-derivatives CEX board reads `cex_oi_radar_rows` and publication state only through `repos.cex_oi_radar.latest_board(...)`; missing rows may be represented as a missing board, but a missing repository is a contract failure. Token Case and Search Inspect read `CexToken` detail only through persisted `cex_detail_snapshots.latest_snapshot(...)`; a missing row can be rendered as structured missing detail, but a missing repository method or route/session binding is a contract failure. Token Case and Search Inspect read market-live state only through persisted current ticks via `latest_market_tick(...)`; a missing row can be rendered as `market_live.status = "missing"`, but a missing repository method is a contract failure. News source status, News fetch contract validation, and runtime News provider-contract status read persisted source/schema state plus a static provider-type contract; they do not inspect the runtime provider object or replace DB schema introspection with code enums. News item-process agent admission reads the just-written deterministic context back through the repository and fails closed if that context is missing. News fetch page dirty targets use the canonical repository's `affected_news_item_ids`; missing affected-set evidence fails the fetch run instead of fabricating a current-item dirty target. News page/brief dirty enqueue always passes raw ids through the repository `servable_news_item_ids` filter; missing filter contract fails closed. Domain wake hints remain hints, not truth, but injected wake objects are runtime contracts: Notification delivery wake, News page-dirty wake, Market Tick Current token-radar wake, and Event Anchor market-tick wake calls must use their required method directly when a wake is due instead of silently accepting malformed wake objects. `WorkerBase` follows the same split for `wake_waiter`: no waiter means interval sleep only, but an injected waiter must expose `wake()`, `async_wait(...)`, and `close()` directly. CEX Market Intel board/detail/series read-model writes use explicit `RepositorySession.transaction` or callable connection transactions; skipped/failed attempt state is not a side channel outside the session transaction, and repository-owned commits cannot fall back to naked `self.conn.commit()`. Narrative Admission dirty-target repository-owned enqueue/claim/done/error/reschedule mutations require a callable connection transaction before queue SQL; `NarrativeRepository` repository-owned `narrative_admissions` upsert/stale mutations require a callable connection transaction before serving-row SQL; `TokenProfileCurrentRepository` repository-owned `token_profile_current` upserts require a callable connection transaction before serving-row SQL; `TokenImageAssetRepository` repository-owned `token_image_assets` pending/ready/error/unsupported lifecycle mutations require a callable connection transaction before image-row SQL, while the TokenImageMirror worker adapter keeps terminal image writes caller-owned inside `RepositorySession.transaction`; `IdentityEvidenceRepository` repository-owned `registry_assets`, `asset_identity_evidence`, and `asset_identity_current` writes require a callable connection transaction before registry/evidence/current identity SQL; `DiscoveryRepository` repository-owned lookup queue/result enqueue, claim, done, reschedule, start, finish, and fail mutations require a callable connection transaction before `token_discovery_dirty_lookup_keys` or `token_discovery_results` SQL; worker paths remain caller-owned inside `RepositorySession.transaction` or ingest `unit_of_work`.

PulseEvidenceBuilder is the sealed evidence-packet boundary before Pulse LLM stages. It reads persisted source events, enriched events, market facts, identity facts, and current discussion digest through the formal evidence source repository methods. Missing repository methods are session/repository wiring failures and must fail before packet construction; empty rows or `None` digest are valid data gaps only after the formal repository method was called.

Pulse evidence packet construction also consumes the formal `PulseCandidateContext` dataclass directly. Dict-like context payloads, `SimpleNamespace` test shims, or `getattr(context, ..., default)` compatibility are not valid runtime input protocols; malformed context fails before sealed packet construction so missing lookup keys cannot masquerade as empty evidence.

Signal Pulse public health is a public read-model concern owned by `PulseReadRepository.freshness_health(...)`. `SignalPulseService` must call that repository method directly; missing method support is route/session wiring failure, while query failure after the method exists may degrade to `pulse_health_query_failed`. The read service must not inspect `repository.conn` or instantiate freshness query services itself.

Macro Sync queue state is an ops/read signal over persisted `macro_sync_windows`. `MacroSyncService.enqueue_due_windows(...)` must call `repos.macro_intel.macro_sync_queue_summary(...)` directly after enqueueing due windows; missing method support is repository/session wiring failure, not an empty queue-summary state.

Asset Market Binance CEX route sync plan counts are ops/read signals over persisted
`cex_tokens` and `price_feeds`. `sync_binance_usdt_perp_routes(...)` must call
`RegistryRepository.binance_usdt_perp_sync_plan_counts(...)` directly for
dry-run/execute summaries; missing method support is repository/session wiring
failure, not an input-count estimate of inserts or deletes.

AssetProfileRepository repository-owned `asset_profiles` ready/status writes
require a callable connection transaction before source-cache SQL. The
AssetProfileRefresh worker service keeps profile writes caller-owned with
`commit=False` inside `RepositorySession.transaction`, so profile source-cache
updates, refresh-target reschedule/error state, and profile-current dirty enqueue
share the worker transaction boundary.

CexTokenProfileRepository repository-owned `cex_token_profiles` ready writes
require a callable connection transaction before source-cache SQL. The
`sync_cex_token_profiles` maintenance service keeps CEX profile writes
caller-owned with `commit=False` inside its service-level connection
transaction.

TokenEvidenceRepository, TokenIntentRepository,
TokenIntentLookupRepository, and IntentResolutionRepository repository-owned
token fact writes require a callable connection transaction before SQL. Ingest,
token intent rebuild, and resolution reprocess keep those writes caller-owned
with `commit=False` inside `unit_of_work` or `RepositorySession.transaction`.
`IntentResolutionRepository` enters the transaction before
`pg_advisory_xact_lock`, so current-resolution serialization remains a real
PostgreSQL transaction property instead of fake/autocommit compatibility.

EvidenceRepository and EntityRepository repository-owned ingest writes require a
callable connection transaction before `raw_frames` input observations or
`event_entities` fact edges write SQL. The collector raw-frame path may own that
small transaction, while full `IngestService.commit_prepared_event(...)` keeps
event entities caller-owned with `commit=False` inside
`EvidenceRepository.unit_of_work` together with events, token facts,
resolution/discovery rows, identity evidence, and dirty targets.

TokenRadarRepository repository-owned serving read-model writes require the
same callable connection transaction before SQL. Default publication enters the
transaction before `pg_advisory_xact_lock`, then writes
`token_radar_current_rows`, `token_radar_publication_state`, target-feature
cache rows, and first-seen rows through the caller-owned `commit=False` path.
Worker projection paths keep these writes inside their existing explicit
projection transaction.

ProjectionRepository repository-owned projection control-plane writes require
the same callable connection transaction before `projection_offsets`,
`projection_runs`, or `projection_dirty_ranges` SQL. Token Radar rank
publication keeps stale-run cleanup, run start/finish, offset advance, and dirty
range operations caller-owned with `commit=False` inside the existing explicit
projection transaction.

TokenRadarRankSourceRepository owns commit boundaries for rank-source edge
mutation and prune paths. Repository-owned `token_radar_rank_source_events`
populate/prune operations enter a callable connection transaction before SQL,
while `TokenRadarRankSourceQuery` remains SQL execution only and has no commit
parameter. Token Radar dirty projection keeps source-edge writes caller-owned
with `commit=False` inside the explicit projection transaction.

TokenFactorEvaluationRepository owns commit boundaries for score-evaluation
read-model writes. Repository-owned single and batch `token_score_evaluations`
upserts enter a callable connection transaction before SQL, and the batch path
keeps each per-row upsert caller-owned with `commit=False` inside that outer
repository transaction.

SignalRepository owns commit boundaries for watched-account token alert writes.
Repository-owned `account_token_alerts` inserts enter a callable connection
transaction before SQL. Evidence ingest keeps alert writes caller-owned with
`commit=False` inside `EvidenceRepository.unit_of_work` after deterministic
token resolution and first-seen checks.

AccountQualityRepository owns commit boundaries for account-quality read-model
tables when it is used outside an outer maintenance transaction.
Repository-owned profile, directory-entry, token-call-stat, and quality snapshot
writes enter a callable connection transaction before SQL. Account Quality
backfill and GMGN directory sync keep those repository writes caller-owned with
`commit=False` inside their explicit maintenance transaction.

NotificationRepository owns commit boundaries for notification facts, read
markers, and delivery control enqueue/requeue writes when it is used outside the
NotificationWorker UoW. Repository-owned notification insert/aggregation and
read-marker writes enter a callable notification connection transaction before
`notifications` or `notification_reads` SQL. Delivery enqueue/requeue enters the
delivery connection transaction before `notification_deliveries` SQL. The
NotificationWorker keeps fact and delivery writes caller-owned with
`commit=False` inside worker-session `unit_of_work`; delivery claim, pre-flight,
log-complete, and external complete/fail state transitions remain owned by
`NotificationDeliveryWorker` session transactions.

AccountQualityBackfillService remains ops-only rather than a manifest worker,
but it is a read-model writer. Its replay of upstream event, resolution,
identity, and market facts into `account_profiles`,
`account_token_call_stats`, and `account_quality_snapshots` enters one callable
connection transaction before backfill reads or writes; missing transaction
support fails with `account_quality_backfill_transaction_required`, not a naked
`conn.commit()` fallback.

Asset Market route/profile/symbol sync services remain explicit maintenance
paths rather than public read helpers. Binance route/profile and Nasdaq Trader
symbol provider reads happen outside DB transactions, while `cex_tokens`,
`price_feeds`, `cex_token_profiles`, and US equity symbol registry writes share
one callable connection transaction. Missing transaction support fails with the
service-specific `*_transaction_required` contract before writes.

Follow-up review found the same RETURNING rowcount evidence gap in US equity
symbol deactivation: `RegistryRepository.deactivate_missing_us_equity_symbols`
updates `us_equity_symbols` through `UPDATE ... RETURNING symbol` and previously
reported returned symbol count through `len(row)`. Target contract is that the
method captures the cursor, fetches rows, returns `_returned_rowcount(cursor,
rows)`, and `_returned_rowcount` first reads `_cursor_rowcount(cursor)` and
requires count to match returned rows. Missing rowcount fails as
`registry_repository_rowcount_required`; invalid or mismatched rowcount fails as
`registry_repository_rowcount_invalid`; architecture guards forbid restored
`return len(row)` or `return len(rows)` accounting
(`src/parallax/domains/asset_market/repositories/registry_repository.py:398`,
`src/parallax/domains/asset_market/repositories/registry_repository.py:420`,
`src/parallax/domains/asset_market/repositories/registry_repository.py:421`,
`src/parallax/domains/asset_market/repositories/registry_repository.py:777`,
`src/parallax/domains/asset_market/repositories/registry_repository.py:789`,
`tests/unit/test_registry_repository.py:151`,
`tests/unit/test_registry_repository.py:163`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:892`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:912`).

Follow-up review found the same SQL evidence gap in Token Image Asset lifecycle
writes. `TokenImageAssetRepository.upsert_pending_sources(...)` writes
`token_image_assets` through `INSERT ... ON CONFLICT ... RETURNING image_id`
and previously counted `affected` from `row is not None`; `mark_ready(...)`
also used `UPDATE ... RETURNING *` without rowcount/RETURNING consistency, while
`mark_error(...)` and `mark_unsupported(...)` executed single-row lifecycle
UPDATEs without validating cursor rowcount. The target contract is that
pending/ready RETURNING paths validate `_single_returning_rowcount(cursor, row)`,
error/unsupported paths validate `_single_rowcount(cursor)`, missing rowcount
fails as `token_image_asset_repository_rowcount_required`, and invalid,
multi-row, or mismatched rowcount fails as
`token_image_asset_repository_rowcount_invalid`
(`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:31`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:62`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:63`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:93`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:122`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:123`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:148`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:166`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:185`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:203`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:267`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:279`,
`src/parallax/domains/asset_market/repositories/token_image_asset_repository.py:286`,
`tests/unit/domains/asset_market/test_token_image_asset_repository.py:137`,
`tests/unit/domains/asset_market/test_token_image_asset_repository.py:191`,
`tests/unit/domains/asset_market/test_token_image_asset_repository.py:211`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1341`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1359`).

Follow-up review found the same RETURNING evidence gap in
`EventAnchorBackfillJobRepository`: `claim_due(...)`, `mark_done(...)`,
`mark_terminal(...)`, terminal retry, stale cleanup helpers, historical ready
reconcile, and temporary `reschedule(...)` all mutate
`event_anchor_backfill_jobs` through `UPDATE ... RETURNING`. The old single-row
paths returned booleans from returned-row presence, while batch paths returned
rows and then counted list length. The target contract is that every
RETURNING-write path captures the cursor, fetches returned rows, validates
`_returned_rowcount(cursor, rows)` or `_single_returning_rowcount(cursor, row)`,
and fails missing, invalid, or mismatched rowcount before worker claim results,
terminal ledger writes, retry results, reconcile counts, or done/reschedule
booleans are reported
(`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:77`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:109`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:190`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:191`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:232`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:233`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:273`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:274`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:335`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:336`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:404`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:448`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:489`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:528`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:529`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:532`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:544`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:551`,
`src/parallax/domains/asset_market/repositories/event_anchor_backfill_job_repository.py:560`,
`tests/unit/test_event_anchor_backfill_job_repository.py:126`,
`tests/unit/test_event_anchor_backfill_job_repository.py:217`,
`tests/unit/test_event_anchor_backfill_job_repository.py:275`,
`tests/unit/test_event_anchor_backfill_job_repository.py:298`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2318`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2320`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2325`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:2326`).

Follow-up review found the same current-row changed-evidence gap in
`TokenProfileCurrentRepository.upsert_current(...)`: the SQL already gates
unchanged public profile/icon rows with `payload_hash IS DISTINCT FROM` and
returns `RETURNING true AS changed`, but the old code classified changed state
from `fetchone()` presence through optional `getattr(..., "fetchone", None)`.
The target contract is that the repository captures the cursor, fetches at most
one returned row, requires PostgreSQL `cursor.rowcount` to be a non-boolean
`0` or `1`, requires rowcount to match returned-row presence, and fails missing
or invalid rowcount before `rows_written` or changed booleans are reported
(`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:123`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:124`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:125`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:181`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:185`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:187`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:193`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:195`,
`src/parallax/domains/asset_market/repositories/token_profile_current_repository.py:197`,
`tests/unit/test_token_profile_current_repository.py:100`,
`tests/unit/test_token_profile_current_repository.py:107`,
`tests/unit/test_token_profile_current_repository.py:115`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1289`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1306`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1310`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1313`).

CLI ops execute commands are maintenance writers rather than runtime workers.
Dry-run paths stay read-only, while token-radar dirty repair, token-capture-tier
rank-set repair, News canonical rebuild enqueue, and GMGN directory sync enter a
callable connection transaction before mutating queues, projection rows, or
directory account fields. GMGN directory client iteration is completed before
the transaction opens.

Queue Ops terminal retry is also an operator control-plane writer. It resolves
`worker_queue_terminal_events` under the platform terminal transaction and
requeues discovery lookup rows, event-anchor jobs, or Pulse agent jobs only
through the formal repositories attached to the same session. Missing retry
repository support fails with the existing operator error and rolls back the
terminal action; it is not treated as an absent queue capability discovered by
optional repository probing.

NotificationDeliveryWorker treats `notification_deliveries` as a
side-effect/control ledger. Delivery claim, pre-flight validation failures,
log-provider complete, and external IO complete/fail transitions run inside
`RepositorySession.transaction` with repository `commit=False`; Apprise and
PushDeer calls happen outside DB transactions. Repository-owned delivery
state-machine writes use a connection transaction when `commit=True`, so tests
and runtime sessions cannot hide missing transaction support behind worker or
repository manual commit.

Token intent rebuild and resolution reprocess are fact/control rebuild paths,
not ad hoc maintenance scripts. `rebuild_recent_token_intents`,
`rebuild_event_token_intents`, and `reprocess_recent_token_intents` enter
`RepositorySession.transaction` before rewriting token evidence/intents,
lookup keys, resolution rows, discovery lookup dirty rows, identity evidence,
or Token Radar source-dirty rows. The inner helpers require the session
transaction and never replace it with `repos.conn.commit()`. `TokenIntentResolver`
is deterministic resolution logic only: it has no commit flag and never commits
resolution rows directly.

MacroViewProjectionWorker publishes Macro current read models as one worker
transaction. It claims one due `macro_projection_dirty_targets` row, refreshes
`macro_observation_series_rows` / publication state, writes the stable current
`macro_view_snapshots` row, and marks the dirty target done with repository
`commit=False` under the same `RepositorySession.transaction`. Projection
failure rolls back partial read-model writes before the worker marks the dirty
target error in the outer transaction. `macro_view_snapshot_updated` is a
post-commit wake hint; unchanged signatures write zero serving snapshot rows and
emit no wake.

TokenRadarProjection dirty work also has one explicit processing transaction.
Worker-level dirty queue lease claims may be committed before processing, but
after due source-event or target dirty rows are acquired, source-edge writes,
target-feature writes/deletes, rank-set publication attempts, and dirty queue
done/error terminalization use caller-owned `commit=False` inside
`conn.transaction()`. Because runtime PostgreSQL connections use
`autocommit=True`, `commit=False` without that explicit transaction is not a
valid delayed commit boundary.

News fetch, item-process, and item-brief writer workers also use
`RepositorySession.transaction` for source reconcile/claim, provider
observation and canonical item writes, deterministic item facts, agent
admission/current brief writes, projection dirty work, and failure state.
Missing session transaction support is a session contract failure before
reconcile, claim, or write, not a raw connection transaction path.

WakeBus emits PostgreSQL `NOTIFY` hints through the dedicated wake pool and
requires callable connection `commit` before the emit completes. WakeWaiter
executes `LISTEN`, commits the listen registration, and requires callable
`notifies` support before blocking for hints. A malformed wake connection is
a runtime contract failure, not a silent local-wait or no-commit fallback;
workers still re-read PostgreSQL on wake and on bounded interval catch-up.

ResolutionRefreshWorker uses `RepositorySession.transaction` for
`start_lookup`, provider-result persistence with `finish_lookup`, error
`fail_lookup` plus retry/terminalize state, and lookup-claim done/reschedule/
terminalize completion. OKX DEX provider IO remains outside the transaction,
but lookup state-machine writes do not call `repos.conn.commit()` directly.

Macro observation-series current refresh uses the connection transaction for
changed current-row delete/insert and publication-state update. Missing
connection transaction support is a repository/session contract failure before
current-row or publication-state SQL, not a `nullcontext` compatibility path.

EventAnchorBackfillJobRepository terminal paths also require a connection
transaction for `event_anchor_backfill_jobs` terminal state and terminal ledger
writes. Missing connection transaction support fails before terminal SQL, not
through `nullcontext` compatibility.

Queue Terminal operator resolution also requires a connection transaction for
`worker_queue_terminal_events` row locking, operator action audit updates, and
registered retry transitions. Missing connection transaction support fails before
the `FOR UPDATE` read, not through `nullcontext` or manual commit compatibility.

DiscoveryRepository terminal lookup paths also require a connection transaction
for claimed `token_discovery_dirty_lookup_keys` delete-returning work and
`worker_queue_terminal_events` terminal ledger writes. Missing connection
transaction support fails before delete or ledger SQL, not through `nullcontext`
or manual commit compatibility.

NewsProjectionDirtyTargetRepository terminal paths also require a connection
transaction for claimed `news_projection_dirty_targets` delete-returning work
and `worker_queue_terminal_events` terminal ledger writes. Missing connection
transaction support fails before delete or ledger SQL, not through
`nullcontext` or manual commit compatibility.

NewsProjectionDirtyTargetRepository ordinary queue mutations also require a
connection transaction for enqueue, due-claim, done, and error writes when the
repository owns the commit. Missing connection transaction support fails before
dirty-target SQL, not through manual commit compatibility.

Ops projection dirty repair keeps dry-run as read-only discovery, but
`--execute` enters the connection transaction before broad repair scans or
dirty-target enqueue. Missing connection transaction support fails before SQL
or queue writes, not through `nullcontext` compatibility.

PulseJobsRepository terminal/dead paths require a connection transaction for
`pulse_agent_jobs` status updates and `worker_queue_terminal_events` terminal
ledger writes. Missing connection transaction support fails before job-state or
ledger SQL, not through `nullcontext` or manual commit compatibility.

PulseAdmissionRepository claim paths require a connection transaction for
`pulse_candidate_edge_state`, `pulse_target_run_budget`, and
`pulse_candidate_run_budget` writes/locks. Missing connection transaction support
fails before edge or budget SQL, not through `nullcontext` compatibility.

TokenCaptureTierWorker also uses `RepositorySession.transaction` for
`token_capture_tier_dirty_targets` claim, `token_capture_tier` tier
write/demotion, and dirty target done state. `project_once(...)` requires an
active session transaction; missing transaction support fails before claim/write,
not through `commit=True` or manual commit compatibility.

## Conceptual data flow

```text
events -> token_intents -> token_intent_resolutions -> stocks-radar DB row query -> /api/stocks-radar
token_discovery_dirty_lookup_keys -> resolution_refresh -> asset_identity facts -> downstream wake hints
notification_deliveries stale running rows -> bounded cleanup batch -> delivery claim
aggregated news_high_signal external push -> enqueue_or_requeue_delivery -> failed/dead delivery reactivation
notification_rule candidate writes -> worker-session unit_of_work -> notifications + notification_deliveries
macro import-bundle envelope -> RepositorySession.unit_of_work -> macro_observations / macro_import_runs / macro_projection_dirty_targets
event_anchor_backfill stale cleanup -> worker-session unit_of_work -> event_anchor_backfill_jobs terminal state + enriched_events terminal lifecycle
EventAnchorBackfillJobRepository terminal paths -> direct callable connection transaction -> event_anchor_backfill_jobs terminal state + worker_queue_terminal_events
token_capture_tier_dirty_targets -> RepositorySession.transaction -> token_capture_tier rows/demotions + dirty done
token_capture_tier_dirty_targets mutation commit=True -> connection transaction -> token_capture_tier_dirty_targets
token_radar facts -> projection publish -> serving rows
token_radar rank publication -> connection transaction -> token_radar_current_rows + token_radar_publication_state + projection_runs
token_radar_source_dirty_events mutation commit=True -> connection transaction -> token_radar_source_dirty_events
token_profile_current_dirty_targets mutation commit=True -> connection transaction -> token_profile_current_dirty_targets
token_image_source_dirty_targets mutation commit=True -> connection transaction -> token_image_source_dirty_targets
asset_profile_refresh_targets mutation commit=True -> connection transaction -> asset_profile_refresh_targets
asset_profiles mutation commit=True -> connection transaction -> asset_profiles
pulse_candidates + freshness query -> Signal Pulse read model -> /api/signal-lab/pulse
low-information Pulse gate -> hide_public_candidate_for_low_information -> hidden public row
token_radar_updated -> pulse_trigger_dirty_targets -> Pulse job/edge/capacity repository reads -> pulse_agent_jobs / pulse_candidate_edge_state
pulse_trigger_dirty_targets -> PulseCandidateWorker -> RepositorySession.transaction -> pulse_candidate_edge_state / pulse_candidates / pulse_agent_jobs / dirty done/error
pulse_agent_jobs -> PulseCandidateJobService -> RepositorySession.transaction -> pulse_agent_runs / pulse_agent_run_steps / pulse_agent_eval_* / pulse_candidates / pulse_playbooks / pulse_candidate_edge_state
pulse_agent_jobs terminal/dead -> connection transaction -> pulse_agent_jobs + worker_queue_terminal_events
pulse job/run mutation commit=True -> connection transaction -> pulse_agent_jobs / pulse_agent_runs
pulse agent repository mutation commit=True -> shared connection transaction -> pulse_agent_runs / pulse_agent_run_steps / pulse_agent_eval_* / pulse_evidence_packets / pulse_candidates / pulse_playbooks / pulse_candidate_edge_state / budget rows
pulse trigger dirty target repository mutation commit=True -> shared connection transaction -> pulse_trigger_dirty_targets
pulse admission claim -> connection transaction -> pulse_candidate_edge_state + pulse_target_run_budget + pulse_candidate_run_budget
macro observation-series refresh -> connection transaction -> macro_observation_series_rows + macro_observation_series_publication_state
macro_view_snapshot_updated -> macro_daily_brief_projection -> macro_daily_briefs(assets_today) -> /api/macro/modules/assets
cex_oi_radar_board -> cex_oi_radar_rows/publication_state -> /api/macro/modules/assets/crypto-derivatives
cex_oi_radar_board -> cex_detail_snapshots -> Token Case / Search Inspect CexToken dossier
market_ticks -> market_tick_current -> Token Case / Search Inspect market_live
account-quality upstream facts -> connection transaction -> account_profiles + account_token_call_stats + account_quality_snapshots
asset-market sync provider reads -> connection transaction -> cex_tokens + price_feeds + cex_token_profiles + registry equity symbols
cex_token_profiles mutation commit=True -> connection transaction -> cex_token_profiles
cli ops execute repair/sync -> connection transaction -> dirty queues + News repair state + GMGN directory rows
profile source facts + token image state -> token_profile_current -> public profile/icon reads
provider logo URL -> token_image_source_dirty_targets -> token_image_assets -> token_profile_current_dirty_targets
news_sources + news_source_quality_rows + static provider type contract -> /api/news/sources/status
news_settings.sources + db schema constraint + static provider type contract -> news_fetch + /api/status provider contract
news_fetch/process/brief writer workers -> RepositorySession.transaction -> news facts / agent admission / current brief / projection dirty work
news_provider_items + canonical upsert/remap cleanup -> affected_news_item_ids -> news_page_dirty_targets
news_item ids -> repository servable filter -> page/brief dirty targets
news_page_dirty_targets -> RepositorySession.transaction -> news_page_rows + dirty done/error
source_quality dirty targets -> RepositorySession.transaction -> news_source_quality_rows + news_sources.source_quality_status + page dirty
news_projection_dirty_targets terminalize -> connection transaction -> queue delete + worker_queue_terminal_events
news_projection_dirty_targets ordinary mutation commit=True -> connection transaction -> news_projection_dirty_targets
ops projection dirty repair --execute -> connection transaction -> repair scan + news_projection_dirty_targets
```

Changed arrows: the stocks-radar arrow to `runtime stock_quote_provider` is removed; `resolution_refresh` is described by its dirty lookup queue input; notification cleanup becomes a bounded batch; notification aggregated external reactivation no longer falls back to insert-only delivery enqueue; notification fact/control writes no longer fall back to `nullcontext` or manual commit when session UoW support is missing; Event Anchor stale cleanup no longer falls back to manual commit when worker-session UoW support is missing; Event Anchor repository terminal paths no longer fall back to `nullcontext` when connection transaction support is missing and no longer use optional transaction probing when that support is malformed; News projection dirty-target terminalization no longer falls back to `nullcontext` or manual commit when connection transaction support is missing; News projection dirty-target ordinary mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Radar source dirty event mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Radar target dirty mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Market Tick Current dirty mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Profile Current dirty mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Image Source dirty mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Asset Profile Refresh target mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Capture Tier dirty mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Token Radar rank publication no longer falls through optional transaction probing or non-contract TypeError when connection transaction support is malformed; ops projection dirty repair execute mode no longer falls back to `nullcontext` when connection transaction support is missing; Pulse job terminal/dead paths no longer fall back to `nullcontext` or manual commit when connection transaction support is missing; Pulse job/run mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Pulse agent write repositories no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Pulse trigger dirty-target repository mutations no longer fall back to manual `self.conn.commit()` when connection transaction support is missing; Pulse admission claims no longer fall back to `nullcontext` when connection transaction support is missing; Macro observation-series current refresh no longer falls back to `nullcontext` when connection transaction support is missing; Token Capture Tier projection no longer claims dirty targets before session transaction and no longer falls back to `commit=True` or manual commit; Macro import-bundle no longer falls back to raw `conn.transaction()` or optional `require_transaction` probing when session UoW support is missing; Pulse candidate job service no longer falls back to `nullcontext` or raw `conn.transaction()` when session transaction support is missing; PulseCandidateWorker no longer falls back to raw `conn.transaction()` when session transaction support is missing; News fetch/process/brief writer workers no longer fall back to raw `conn.transaction()` when session transaction support is missing; News page/source-quality projection workers no longer fall back to `nullcontext` or raw `conn.transaction()` when session transaction support is missing; Token Radar publish no longer invokes retention prune; Pulse read no longer traverses event ids through JSONB expansion, no longer reads scheduler liveness, no longer treats low-information hide as an optional no-op, and no longer treats missing dirty-trigger job/edge/capacity/queue-depth repository methods as empty control-plane state; Macro assets daily brief no longer treats a missing repository read method as an empty brief; Macro crypto-derivatives CEX board no longer treats a missing repository as an omitted board; Token Case CEX detail no longer treats missing snapshot repository support as omitted detail, and Search Inspect no longer builds token-result dossiers without the same snapshot repository; Token Case market-live no longer treats missing latest-market-tick repository support as a missing market snapshot; News source status and News provider-contract validation no longer read runtime provider objects for static capabilities or use Python enums as a DB schema fallback; News fetch no longer invents dirty targets from the current item id when repository affected-set evidence is absent; News projection work no longer bypasses the repository servable filter when the filter method is missing.

Asset Profile source-cache mutations no longer fall back to manual
`self.conn.commit()` when connection transaction support is missing; worker
profile writes stay caller-owned inside the refresh worker session transaction.
CEX Token Profile source-cache mutations no longer fall back to manual
`self.conn.commit()` when connection transaction support is missing; sync
service writes stay caller-owned inside its connection transaction.

## Core models

`StocksRadarData` remains a social attention read contract. Its quote block may report `status = "unavailable"` with `error = "quote_read_model_unavailable"` to state that no persisted quote read model exists.

`resolution_refresh` owns due lookup keys in `token_discovery_dirty_lookup_keys` and writes refreshed identity facts plus queue completion state.

`notification_deliveries` running rows older than the timeout are reclaimed or terminalized only through bounded, indexed batches.

Aggregated `news_high_signal` external delivery reactivation uses `notification_deliveries(notification_id, channel_id)` conflict semantics through `enqueue_or_requeue_delivery`; insert-only delivery enqueue is only for new notification rows.

Event Anchor stale cleanup writes `event_anchor_backfill_jobs` terminal or rescheduled control state and matching `enriched_events` terminal lifecycle state inside worker-session `unit_of_work`. Missing session UoW support is a worker/session contract failure before cleanup writes.

Event Anchor repository terminal paths write `event_anchor_backfill_jobs` terminal state and `worker_queue_terminal_events` inside the connection transaction. Missing or non-callable connection transaction support is a repository/session contract failure before terminal SQL; the helper reads the formal `conn.transaction` contract directly instead of using optional probing.

Queue Terminal operator resolution updates `worker_queue_terminal_events.operator_action` and invokes retry transitions inside the connection transaction. Missing connection transaction support is a platform/session contract failure before `SELECT ... FOR UPDATE`.

Queue Terminal source-row terminalization uses the same connection transaction contract when `terminalize_source_row(..., commit=True)` owns the commit. Missing connection transaction support fails before terminal generation reads or terminal ledger inserts; platform terminalization must not preserve a naked `conn.commit()` path.

DiscoveryRepository terminal lookup claims delete claimed `token_discovery_dirty_lookup_keys` rows and write `worker_queue_terminal_events` inside the connection transaction. Missing connection transaction support is a repository/session contract failure before delete/ledger SQL.

NewsProjectionDirtyTargetRepository terminal paths delete claimed `news_projection_dirty_targets` rows and write `worker_queue_terminal_events` inside the connection transaction. Missing connection transaction support is a repository/session contract failure before delete/ledger SQL.

NewsProjectionDirtyTargetRepository ordinary queue mutations enqueue changed targets,
claim due targets, delete completed claims, and retry errored claims inside the
connection transaction when the repository owns the commit. Missing connection
transaction support is a repository/session contract failure before queue SQL.

Ops projection dirty repair executes News dirty-target enqueue inside a connection transaction. Dry-run may report counts read-only, but `--execute` fails before repair scans or queue writes when connection transaction support is missing.

PulseJobsRepository terminal/dead paths update `pulse_agent_jobs` and write `worker_queue_terminal_events` inside the connection transaction. Missing connection transaction support is a repository/session contract failure before job-state or terminal-ledger SQL.

PulseJobsRepository job/run mutation paths enqueue jobs, mark success, release running jobs, and fail stale `pulse_agent_runs` inside the connection transaction when the repository owns the commit. Missing connection transaction support is a repository/session contract failure before job/run SQL.

Pulse agent write repository mutation paths write agent runs, run steps, eval
versions/cases/results, evidence packets, candidate rows, playbook rows, and
ordinary admission edge/budget state inside the shared Pulse connection
transaction when the repository owns the commit. Missing connection transaction
support is a repository/session contract failure before agent write SQL.

Pulse trigger dirty-target repository mutation paths enqueue changed targets,
claim due targets, delete completed claims, retry errored claims, and reschedule
claims inside the shared Pulse connection transaction when the repository owns
the commit. Missing connection transaction support is a repository/session
contract failure before dirty-target SQL.

PulseAdmissionRepository claim paths update `pulse_candidate_edge_state`, lock and update `pulse_target_run_budget`, and lock and update `pulse_candidate_run_budget` inside the connection transaction. Missing connection transaction support is a repository/session contract failure before edge or budget SQL.

Macro observation-series current refresh deletes exited `macro_observation_series_rows`, inserts/updates changed current rows, and updates `macro_observation_series_publication_state` inside the connection transaction. Missing connection transaction support is a repository/session contract failure before current-row or publication-state SQL.

`token_capture_tier` stores the current rebuildable market-capture control projection. Its dirty target claim, tier row writes/demotions, and dirty target done state share `RepositorySession.transaction`; `project_once(...)` requires an active session transaction and never commits manually.

Token Capture Tier dirty queue mutation paths enqueue rank-set recompute work,
claim due work, and delete completed claims inside the connection transaction
when the repository owns the commit. Missing connection transaction support is a
repository/session contract failure before `token_capture_tier_dirty_targets`
SQL.

Token Radar rank publication writes current rows, publication state, offset
advance, and run finish inside one connection transaction. Missing or
non-callable connection transaction support is a projection/session contract
failure before `publish_current_generation(...)` side effects.

Token Profile Current dirty queue mutation paths enqueue profile-current targets,
claim due targets, delete completed claims, and retry errored claims inside the
connection transaction when the repository owns the commit. Missing connection
transaction support is a repository/session contract failure before
`token_profile_current_dirty_targets` SQL.

Token Image Source dirty queue mutation paths enqueue image source targets,
claim due targets, delete completed claims, and retry errored claims inside the
connection transaction when the repository owns the commit. Missing connection
transaction support is a repository/session contract failure before
`token_image_source_dirty_targets` SQL.

Asset Profile Refresh target queue mutation paths enqueue provider profile
refresh targets, claim due targets, reschedule claimed targets, and retry
errored claims inside the connection transaction when the repository owns the
commit. Missing connection transaction support is a repository/session contract
failure before `asset_profile_refresh_targets` SQL.

Macrodata bundle imports write `macro_observations`, `macro_import_runs`, and `macro_projection_dirty_targets` inside a formal `RepositorySession.unit_of_work`. `write_macrodata_bundle_import` requires an active session transaction through `repos.require_transaction(...)` and does not open raw connection transactions by itself.

`macro_daily_briefs` stores stable daily brief read-model rows keyed by `brief_key`, currently `assets_today`. `/api/macro/modules/assets` reads that model through `MacroIntelRepository.latest_macro_daily_brief`; the row may be absent, but the repository method is not optional.

`cex_oi_radar_rows` and `cex_oi_radar_publication_state` store the current derivatives board. `/api/macro/modules/assets/crypto-derivatives` reads that model through `CexOiRadarRepository.latest_board`; missing rows are represented in the repository result, but the repository itself is not optional.

`cex_detail_snapshots` stores the current single-token CEX detail payload. Token Case and Search Inspect read that model through `CexDetailSnapshotRepository.latest_snapshot`; missing rows produce structured missing detail for `CexToken`, but the repository method itself is not optional.

`market_tick_current` stores the latest persisted market tick per target. Token Case and Search Inspect read that state through `TokenTargetRepository.latest_market_tick`; missing rows produce structured missing market-live state, but the repository method itself is not optional.

`token_radar_rows` publication is separate from retention cleanup of private cache rows and rank-source edges.
Follow-up review closed the remaining private-cache ownership gap: `TokenRadarProjectionWorker` owns the maintenance lane, `private_cache_retention_ms` is a formal worker setting, the worker calls `prune_private_cache`, and target-feature / rank-source prune SQL is bounded by `LIMIT %s` (`src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py:20`, `src/parallax/platform/config/settings.py:1013`, `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py:248`, `src/parallax/domains/token_intel/repositories/token_radar_repository.py:638`, `src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py:163`).

`pulse_candidates` public reads filter by indexed candidate identity or supported compact edges, not by expanding candidate JSONB arrays.

Pulse low-information gating updates existing public rows to `hidden_blocked_low_information` through the Pulse candidates repository. Missing hide support fails the dirty trigger, preserving retry visibility instead of leaving stale public rows.

Pulse dirty-trigger admission reads `pulse_agent_jobs`, `pulse_candidate_edge_state`, recent failure counts, pending job counts, and trigger queue depth through the formal Pulse repositories. Missing repository methods fail dirty triggers for retry instead of being interpreted as empty state.

Pulse candidate job execution writes `pulse_agent_runs`, `pulse_agent_run_steps`, deterministic `pulse_agent_eval_*` rows, `pulse_candidates`, `pulse_playbooks`, admission edge state, and `pulse_agent_jobs` terminal state inside `RepositorySession.transaction`. Missing session transaction support is a worker/session contract failure before writes.

PulseCandidateWorker dirty-trigger execution writes trigger claim/terminal state, admission/edge state, public visibility transitions, and `pulse_agent_jobs` enqueue state inside `RepositorySession.transaction`. Missing session transaction support is a worker/session contract failure before dirty target claim or writes.

News page and source-quality projection execution writes `news_page_rows`, `news_source_quality_rows`, `news_sources.source_quality_status`, downstream page dirty rows, and dirty-target done/error state inside `RepositorySession.transaction`. Missing session transaction support is a worker/session contract failure before claim/write.

News fetch, item-process, and item-brief execution writes `news_sources`,
`news_fetch_runs`, `news_provider_items`, `news_items`,
`news_item_entities`, `news_token_mentions`, `news_fact_candidates`,
`news_items.agent_admission_*`, `news_item_agent_runs`,
`news_item_agent_briefs`, projection dirty work, and claim/failure state inside
`RepositorySession.transaction`. Missing session transaction support is a
worker/session contract failure before reconcile, claim, or write.

## Interface contracts

`GET /api/stocks-radar` keeps `window`, `scope`, and `limit` validation semantics. It no longer performs provider IO. Rows return social attention fields and a quote block with `status = "unavailable"`, null numeric fields, and `error = "quote_read_model_unavailable"` until a future persisted quote read model is introduced.

`resolution_refresh` CLI and scheduler behavior remain worker-based. Tests and internal imports must not call `run_resolution_refresh_once` because that helper is removed.

Notification delivery public behavior remains unchanged: workers can reclaim retryable stale running rows and terminalize exhausted stale running rows. The implementation changes only the SQL shape and index support.

Notification rule external delivery behavior remains explicit: new notification rows may call `enqueue_delivery`, while aggregated high-signal rows that should reactivate failed/dead external push deliveries must call `enqueue_or_requeue_delivery`. Missing requeue contract is a worker/repository contract failure, not a compatibility path.

Notification rule transaction behavior is explicit: `NotificationWorker` must enter `repos.unit_of_work()` before evaluating and writing candidates. Missing session UoW support is a worker/session contract failure and must fail before writes; runtime code must not use `nullcontext`, optional UoW probing, or manual repository commit fallback.

Macrodata bundle import transaction behavior is explicit: `import_macrodata_bundle` must enter `repos.unit_of_work()` before writing observations, import runs, or projection dirty targets, and `write_macrodata_bundle_import` must call `repos.require_transaction(...)` directly. Missing session UoW or transaction guard support is a session contract failure, not permission to use `conn.transaction()` fallback.

Pulse public handle filtering may narrow to direct candidate subject matching unless an existing compact, indexable edge can support author-handle lookup without JSONB expansion.

Pulse low-information public-row hiding is part of the worker write contract. If `hide_public_candidate_for_low_information` is absent, the dirty trigger must be marked failed/retryable rather than done.

Pulse dirty-trigger state and capacity reads call `job_for_candidate`, `edge_state_by_candidate`, `recent_target_failure_count`, `pending_agent_job_count`, `pending_agent_job_count_for_window_scope`, and `pulse_trigger_dirty_targets.queue_depth` directly. Missing methods are worker/repository contract failures, not empty state.

Pulse candidate job service transaction behavior is explicit: every write block uses `repos.transaction()`. A repository session without `transaction` fails before agent ledger, eval, candidate, playbook, admission, or job terminal writes; runtime code must not use `nullcontext`, optional transaction probing, or raw connection transactions as compatibility fallback.

Pulse jobs repository mutation transaction behavior is explicit: `commit=True` enters the connection transaction through `_run_job_write`, while `commit=False` is used only when the caller owns an outer session transaction. A connection without `transaction` fails before job/run SQL; repository code must not use manual `self.conn.commit()` compatibility.

Pulse candidate worker transaction behavior is explicit: dirty-trigger claim, admission/edge/public visibility writes, job enqueue, and dirty target done/error updates use `repos.transaction()` directly. A repository session without `transaction` fails before dirty target claim or writes; runtime code must not use optional transaction probing or raw connection transactions as compatibility fallback.

Signal Pulse public health reports persisted readiness, counts, freshness, and publish status only. Scheduler or worker liveness stays in `/api/status` and related ops diagnostics.

News source status reports static runtime-supported provider types together with configured source provider types and hygiene warnings. News provider-contract validation in fetch/status paths uses the same static runtime-supported provider types plus the live database schema constraint values. These paths must not read `runtime.providers`, provider client objects, feed-client capability methods, private registry attributes, or Python source-classification enums as schema fallback.

News fetch treats `affected_news_item_ids` as part of the canonical upsert repository contract for inserted/updated items. If the repository omits that set, the worker fails the fetch run and emits no downstream page dirty target or wake for the item.

News projection dirty enqueue treats `servable_news_item_ids` as part of the repository contract. If a repository implementation omits that filter, page/brief dirty enqueue fails closed before writing projection dirty targets.

News page/source-quality projection transaction behavior is explicit: claim, read-model writes, downstream dirty enqueue, and done/error marking use `repos.transaction()` directly. A repository session without `transaction` fails before dirty target claim or read-model writes; runtime code must not use `nullcontext`, optional transaction probing, or raw connection transactions as compatibility fallback.

News fetch/process/brief writer transaction behavior is explicit: source
reconcile/claim, provider observation and canonical item writes, deterministic
item fact writes, agent admission/current brief writes, projection dirty enqueue,
and failure state use `repos.transaction()` directly. A repository session
without `transaction` fails before reconcile, claim, or write; runtime code must
not use raw connection transactions as compatibility fallback.

Event Anchor stale cleanup transaction behavior is explicit: stale job terminalization/reschedule and matching enriched-event terminal lifecycle writes use worker-session `unit_of_work` through `_transaction_session()`. A repository session without `unit_of_work` fails before cleanup writes; runtime code must not probe for repository or connection `commit()` as compatibility fallback.

Event Anchor repository terminal transaction behavior is explicit: `expire_stale(...)` and `mark_terminal(...)` use the connection transaction for event-anchor job terminal state and terminal ledger writes. A connection without `transaction` fails before SQL; repository code must not use `nullcontext` or optional transaction probing as compatibility fallback.

News projection dirty-target terminal transaction behavior is explicit: `terminalize_targets(...)` uses the connection transaction for claimed dirty-target delete and terminal ledger writes. A connection without `transaction` fails before SQL; repository code must not use `nullcontext`, manual commit, or optional transaction probing as compatibility fallback.

Ops projection dirty repair transaction behavior is explicit: dry-run uses the explicit read-only `nullcontext` branch, while execute mode calls `_transaction(repos.conn)` and raises `projection_dirty_targets_transaction_required` when the connection transaction contract is missing. Execute mode must not run repair scans or dirty-target enqueue under `nullcontext`.

Macro observation-series refresh transaction behavior is explicit: changed current-row delete/insert and `macro_observation_series_publication_state` update use the connection transaction. A connection without `transaction` fails before current-row or publication-state SQL; repository code must not use `nullcontext` or optional transaction probing as compatibility fallback.

Token Capture Tier projection transaction behavior is explicit: dirty target claim, `token_capture_tier` row write/demotion, and dirty target done marking use `repos.transaction()` directly, and `project_once(...)` requires `repos.require_transaction(operation="token_capture_tier_projection")`. A repository session without `transaction` fails before dirty target claim or tier writes; runtime code must not use `commit=True`, optional commit probing, or manual `commit()` compatibility.

Token Radar source-edge dirty work treats `token_radar_source_dirty_events` as a required PostgreSQL queue contract. Ingest and resolution reprocess enqueue source-event edges, and projection workers claim that queue; missing repository contract must fail closed rather than being interpreted as no work.

TokenRadarSourceDirtyEventRepository source-edge queue mutations enqueue resolved
source-event edges, claim due source edges, delete completed claims, and retry
errored claims inside the connection transaction when the repository owns the
commit. Missing connection transaction support is a repository/session contract
failure before queue SQL.

TokenRadarDirtyTargetRepository target queue mutations enqueue source, market,
repair, and bounded catch-up dirty targets, claim due target work, delete
completed claims, and retry errored claims inside the connection transaction
when the repository owns the commit. Missing connection transaction support is
a repository/session contract failure before `token_radar_dirty_targets` SQL.

TokenRadarProjection downstream dirty-target fan-out uses direct session
repositories for Pulse trigger, Narrative Admission, Token Profile Current, and
Token Capture Tier dirty queues after rank-set changes. Missing downstream
repositories are projection session wiring failures; runtime code must not use
optional repository probes or custom missing-repository branches as compatibility
fallback.

MarketTickCurrentDirtyTargetRepository queue mutations enqueue changed market
targets, claim due current-market projection work, delete completed claims, and
retry errored claims inside the connection transaction when the repository owns
the commit. Missing connection transaction support is a repository/session
contract failure before `market_tick_current_dirty_targets` SQL.

Macro assets daily brief public reads call `latest_macro_daily_brief` directly. Missing `assets_today` data can be represented as no brief, but a missing repository method is not compatible with a successful route response.

Macro crypto-derivatives public reads call `cex_oi_radar.latest_board` directly. Missing CEX board rows can be represented as a missing board, but a missing repository/session contract is not compatible with a successful route response.

Token Case and Search Inspect CEX token-result reads call `cex_detail_snapshots.latest_snapshot` directly. Missing CEX detail rows can be represented as a structured missing detail block, but a missing repository/session contract is not compatible with a successful dossier response.

Token Case and Search Inspect market-live reads call `latest_market_tick` directly. Missing current tick rows can be represented as `market_live.status = "missing"`, but a missing repository/session contract is not compatible with a successful dossier response.

Token profile current projection reads profile source facts through `RepositorySession.source_query` directly. Missing profile source rows can produce explicit missing/unsupported profile state, but a missing session query contract must fail the dirty target instead of being hidden by constructing `TokenProfileSourceQuery(repos.conn)` in the worker.

NewsRepository default writes now share the same transaction contract as the
News worker paths. Repository-owned writes require a callable connection
transaction before SQL; worker/session paths pass `commit=False` inside
`RepositorySession.transaction` and do not rely on repository-owned commits
(`src/parallax/domains/news_intel/ARCHITECTURE.md:186`).

News deterministic fact value objects now live below services in the domain
types layer: repositories import `NewsEntity`, `NewsTokenMention`, and
`NewsFactCandidate` from that layer, while the architecture harness rejects
repository/query imports from `.services.`, `.runtime.`, or `.read_models.`
(`src/parallax/domains/news_intel/types/news_extraction.py:7`,
`src/parallax/domains/news_intel/types/news_extraction.py:23`,
`src/parallax/domains/news_intel/types/news_extraction.py:43`,
`src/parallax/domains/news_intel/repositories/news_repository.py:29`,
`tests/architecture/test_src_domain_architecture.py:341`,
`tests/architecture/test_src_domain_architecture.py:348`).

MacroIntelRepository projection dirty-target default claim/done/error writes
now share the same transaction contract as the Macro projection worker path.
Repository-owned writes require a callable connection transaction before
`macro_projection_dirty_targets` SQL; worker/session paths pass `commit=False`
inside `RepositorySession.transaction`.

WorkerScheduler status and liveness now use `status_payload()` as a direct
runtime worker contract (`src/parallax/app/runtime/worker_scheduler.py:86`,
`src/parallax/app/runtime/worker_scheduler.py:151`,
`src/parallax/app/runtime/worker_scheduler.py:178`). Missing hooks, raised hook
errors, or non-object payloads fail visibly instead of being converted to
stopped/empty status, with unit and architecture guards covering the contract
(`tests/unit/test_worker_scheduler.py:254`,
`tests/architecture/test_worker_runtime_contracts.py:272`).

API dependency helpers apply the same status contract when routes need worker
liveness or direct access to a route-local worker. `_worker_running(...)` reads
`runtime.scheduler`, `scheduler.tasks`, and direct scheduler status payloads,
while `_worker_object(...)` reads `runtime.scheduler.workers` and validates the
worker's own payload before returning the object
(`src/parallax/app/surfaces/api/dependencies.py:36`,
`src/parallax/app/surfaces/api/dependencies.py:45`,
`src/parallax/app/surfaces/api/dependencies.py:55`,
`src/parallax/app/surfaces/api/dependencies.py:65`). Unit and architecture
guards prove missing/raising/non-object status hooks fail visibly instead of
becoming false liveness or unsupported routes
(`tests/unit/test_api_dependencies.py:54`,
`tests/unit/test_api_dependencies.py:80`,
`tests/architecture/test_worker_runtime_contracts.py:292`).

Discovery lookup terminalization now treats the deleted queue row payload hash as
terminal evidence, not as an optional display field. `terminalize_lookup_claims`
passes `_terminal_source_payload_hash(row)` into the queue terminal ledger call
(`src/parallax/domains/asset_market/repositories/discovery_repository.py:423`),
and `_terminal_source_payload_hash(...)` reads `row["payload_hash"]` directly
before accepting the row
(`src/parallax/domains/asset_market/repositories/discovery_repository.py:762`,
`src/parallax/domains/asset_market/repositories/discovery_repository.py:767`).
Focused unit and architecture guards require malformed deleted source rows to
fail before `worker_queue_terminal_events` SQL and forbid the previous
`row.get("payload_hash") or ""` fallback
(`tests/unit/test_discovery_repository.py:280`,
`tests/unit/test_discovery_repository.py:292`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1326`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1330`).

Macro observation-series current refresh now treats existing current-row
`payload_hash` as a required read-model signature before changed/unchanged
comparison. `_series_payload_hashes_by_concept(...)` calls
`_existing_series_payload_hash(row)` for existing rows
(`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1963`),
and `_existing_series_payload_hash(...)` reads `row["payload_hash"]` directly
(`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1977`,
`src/parallax/domains/macro_intel/repositories/macro_intel_repository.py:1979`).
Focused unit and architecture guards prove malformed existing current rows fail
before delete/insert SQL and forbid the previous
`str(row.get("payload_hash") or "")` / `row.get("payload_hash") or ""`
fallback
(`tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py:91`,
`tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py:105`,
`tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py:116`,
`tests/architecture/test_macro_kappa_contract.py:20`,
`tests/architecture/test_macro_kappa_contract.py:23`,
`tests/architecture/test_macro_kappa_contract.py:25`).

Stocks Radar public SQL now treats event-id provenance as bounded response
metadata instead of an unbounded public read payload. The query defines
`STOCKS_RADAR_SOURCE_EVENT_LIMIT = 25`, ranks stock mentions per target through
`ranked_mentions AS MATERIALIZED` and `row_number()`, and aggregates
`source_event_ids` only through `FILTER (WHERE event_rank <= %s)` while leaving
mentions, unique authors, watched mentions, and latest evidence over the full
requested window
(`src/parallax/domains/token_intel/queries/stocks_radar_query.py:7`,
`src/parallax/domains/token_intel/queries/stocks_radar_query.py:53`,
`src/parallax/domains/token_intel/queries/stocks_radar_query.py:56`,
`src/parallax/domains/token_intel/queries/stocks_radar_query.py:76`,
`src/parallax/domains/token_intel/queries/stocks_radar_query.py:106`).
Focused unit and architecture guards require the ranked CTE and bounded
aggregate, and forbid the previous unbounded
`ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids`
shape in the read path
(`tests/unit/test_stocks_radar_query.py:27`,
`tests/unit/test_stocks_radar_query.py:29`,
`tests/unit/test_stocks_radar_query.py:30`,
`tests/architecture/test_api_read_paths_provider_free.py:46`,
`tests/architecture/test_api_read_paths_provider_free.py:47`,
`tests/architecture/test_api_read_paths_provider_free.py:48`).

News agent-admission duplicate lookup now uses normalized provider-article edge
rows instead of expanding `provider_article_keys_json`. `_agent_exact_duplicate_context(...)`
materializes the target item's `news_item_observation_edges.provider_article_key`
values and joins candidates through the same edge table
(`src/parallax/domains/news_intel/repositories/news_repository.py:2775`,
`src/parallax/domains/news_intel/repositories/news_repository.py:2777`,
`src/parallax/domains/news_intel/repositories/news_repository.py:2790`,
`src/parallax/domains/news_intel/repositories/news_repository.py:2791`).
`load_agent_admission_contexts(...)` likewise self-joins target provider edges to
duplicate provider edges, keeping `provider_article_keys_json` as payload evidence
rather than an index structure
(`src/parallax/domains/news_intel/repositories/news_repository.py:3309`,
`src/parallax/domains/news_intel/repositories/news_repository.py:3312`,
`src/parallax/domains/news_intel/repositories/news_repository.py:3313`,
`src/parallax/domains/news_intel/repositories/news_repository.py:3316`,
`src/parallax/domains/news_intel/repositories/news_repository.py:3317`).
Focused unit and architecture guards require `target_provider_edges`, the
provider-article edge join, and no `jsonb_array_elements_text` expansion in these
agent-admission duplicate lookup functions
(`tests/unit/domains/news_intel/test_news_repository_queries.py:90`,
`tests/unit/domains/news_intel/test_news_repository_queries.py:91`,
`tests/unit/domains/news_intel/test_news_repository_queries.py:92`,
`tests/architecture/test_news_intel_kiss_simplification.py:697`,
`tests/architecture/test_news_intel_kiss_simplification.py:705`,
`tests/architecture/test_news_intel_kiss_simplification.py:711`,
`tests/architecture/test_news_intel_kiss_simplification.py:713`).

Follow-up review found the same changed-row accounting gap in notification
read-marker writes. `NotificationRepository` already required transaction
ownership for `notification_reads`, but `mark_all_read(...)` and
`mark_author_read(...)` still returned changed counts from `len(rows)`, and
`mark_read(...)` returned success without validating the read-marker UPSERT
cursor evidence. The target contract is that `mark_read(...)` uses single-row
PostgreSQL rowcount evidence, while `mark_all_read(...)` and
`mark_author_read(...)` use one `INSERT ... SELECT ... RETURNING` cursor whose
rowcount matches the returned rows through `_returned_write_count(...)`
(`src/parallax/domains/notifications/repositories/notification_repository.py:24`,
`src/parallax/domains/notifications/repositories/notification_repository.py:464`,
`src/parallax/domains/notifications/repositories/notification_repository.py:482`,
`src/parallax/domains/notifications/repositories/notification_repository.py:491`,
`src/parallax/domains/notifications/repositories/notification_repository.py:504`,
`src/parallax/domains/notifications/repositories/notification_repository.py:515`,
`src/parallax/domains/notifications/repositories/notification_repository.py:524`,
`src/parallax/domains/notifications/repositories/notification_repository.py:548`,
`src/parallax/domains/notifications/repositories/notification_repository.py:559`,
`src/parallax/domains/notifications/repositories/notification_repository.py:930`,
`src/parallax/domains/notifications/repositories/notification_repository.py:949`,
`tests/unit/test_notification_worker_runtime.py:631`,
`tests/unit/test_notification_worker_runtime.py:660`,
`tests/architecture/test_notifications_hard_cut.py:407`,
`tests/architecture/test_notifications_hard_cut.py:423`,
`tests/architecture/test_notifications_hard_cut.py:430`).

Follow-up review found that Token Radar generic dirty enqueue paths still
reported candidate `len(records)` instead of PostgreSQL changed-row evidence.
`TokenRadarDirtyTargetRepository` now makes `enqueue_targets(...)` return
`_cursor_rowcount(cursor)` for `token_radar_dirty_targets`, and
`TokenRadarSourceDirtyEventRepository` now makes `enqueue_events(...)` return
`_cursor_rowcount(cursor)` for `token_radar_source_dirty_events`, preserving the
contract that target/source dirty queue enqueue counts come from PostgreSQL
rowcount rather than application-side candidate width
(`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:43`,
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:57`,
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:61`,
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:360`,
`src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py:381`,
`src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:19`,
`src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:33`,
`src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:45`,
`src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:100`,
`src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py:439`,
`tests/unit/test_token_radar_dirty_target_repository.py:229`,
`tests/unit/test_token_radar_dirty_target_repository.py:242`,
`tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py:196`,
`tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py:210`,
`tests/architecture/test_token_radar_source_width_contract.py:228`,
`tests/architecture/test_token_radar_source_width_contract.py:258`).

Follow-up review found the same candidate-width accounting leak in News
projection dirty enqueue. `NewsProjectionDirtyTargetRepository.enqueue_targets(...)`
now captures the PostgreSQL cursor for `news_projection_dirty_targets` and
returns `_cursor_rowcount(cursor)`, preserving the contract that dirty enqueue
counts come from PostgreSQL changed-row evidence rather than application-side
`len(records)`
(`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:19`,
`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:38`,
`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:62`,
`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:96`,
`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:161`,
`src/parallax/domains/news_intel/repositories/news_projection_dirty_target_repository.py:610`,
`tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:313`,
`tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:325`,
`tests/unit/domains/news_intel/test_news_projection_dirty_targets.py:338`,
`tests/architecture/test_news_intel_kiss_simplification.py:437`,
`tests/architecture/test_news_intel_kiss_simplification.py:443`,
`tests/architecture/test_news_intel_kiss_simplification.py:447`,
`tests/architecture/test_news_intel_kiss_simplification.py:448`).

Follow-up review found the same candidate-width accounting leak in Market Tick
Current dirty enqueue. The `enqueue_targets` path now captures the PostgreSQL
cursor for `market_tick_current_dirty_targets` and returns
`_cursor_rowcount(cursor)`, preserving the contract that dirty enqueue counts
come from PostgreSQL changed-row evidence rather than application-side
`len(records)`
(`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:14`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:27`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:37`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:67`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:81`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:97`,
`src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py:387`,
`tests/unit/test_market_tick_current_repository.py:226`,
`tests/unit/test_market_tick_current_repository.py:239`,
`tests/unit/test_market_tick_current_repository.py:253`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1488`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1489`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1490`,
`tests/architecture/test_runtime_worker_constraint_hard_cut.py:1491`).

## Acceptance criteria

- AC1. WHEN `/api/stocks-radar` is served THEN system SHALL build the response from PostgreSQL read queries without accessing any runtime quote provider.
- AC2. WHEN `StocksRadarService` sees rows that need quote data THEN system SHALL return `quote.status = "unavailable"` with `error = "quote_read_model_unavailable"` and no provider request.
- AC3. WHEN worker contracts are inspected THEN system SHALL classify `resolution_refresh` as a dirty lookup queue consumer over `token_discovery_dirty_lookup_keys`.
- AC4. WHEN resolution refresh tests or callers need one pass of work THEN system SHALL use `ResolutionRefreshWorker.run_once` or pure fetch/persist helpers, with no `run_resolution_refresh_once` compatibility helper.
- AC5. WHEN notification delivery claims run against many stale exhausted running rows THEN system SHALL terminalize them through an indexed, bounded, skip-locked batch.
- AC6. WHEN Token Radar rank sets are published THEN system SHALL avoid retention prune calls from the publish hot path.
- AC7. WHEN Pulse public read SQL is inspected THEN system SHALL contain no `jsonb_array_elements_text` expansion in `pulse_read_repository.py`.
- AC8. WHEN `/api/signal-lab/pulse` public contracts are inspected THEN system SHALL expose no worker or scheduler liveness field and SHALL not call `_worker_running` from that read path.
- AC9. WHEN News source status, News fetch provider-contract validation, or runtime News provider-contract status is evaluated THEN system SHALL build supported provider-type evidence from the static runtime provider-type contract and schema evidence from the live DB constraint, without reading runtime provider objects, feed-client capability methods, private registries, or Python provider-type enum fallbacks.
- AC10. WHEN the feature is completed THEN system SHALL have SDD validation, targeted tests, and `make check-all` evidence recorded in `verification.md`; if integration-heavy verification is suspended, the SDD record SHALL remain `In Progress`.
- AC11. WHEN `NewsItemProcessWorker` computes agent admission THEN system SHALL use repository readback for item/entities/token_mentions/fact_candidates and SHALL fail closed without writing agent admission when that context is missing or incomplete.
- AC12. WHEN `NewsFetchWorker` persists inserted or updated canonical news items THEN system SHALL enqueue page dirty targets only from repository-returned `affected_news_item_ids` and SHALL fail closed if that set is missing or empty.
- AC13. WHEN News page or item-brief dirty work is enqueued from item ids THEN system SHALL require the repository `servable_news_item_ids` filter and SHALL fail closed without enqueueing if the filter contract is absent.
- AC14. WHEN Token Radar source-event facts are ingested, reprocessed, or projected THEN system SHALL require `token_radar_source_dirty_events` repository enqueue/claim contracts and SHALL fail closed instead of treating missing contracts as empty work.
- AC15. WHEN an aggregated notification should reactivate an external delivery THEN system SHALL require `enqueue_or_requeue_delivery` and SHALL not fall back to insert-only `enqueue_delivery` when that contract is missing.
- AC16. WHEN Pulse low-information gating needs to hide an existing public candidate THEN system SHALL require `hide_public_candidate_for_low_information` and SHALL fail the dirty trigger for retry if that contract is missing.
- AC17. WHEN `/api/macro/modules/assets` reads the assets daily brief THEN system SHALL require `latest_macro_daily_brief` and SHALL not fall back to `None` when that repository method is missing.
- AC18. WHEN `/api/macro/modules/assets/crypto-derivatives` reads the CEX board THEN system SHALL require `cex_oi_radar.latest_board` and SHALL not fall back to omitting the board when that repository is missing.
- AC19. WHEN Token Case or Search Inspect builds a `CexToken` dossier THEN system SHALL require `cex_detail_snapshots.latest_snapshot` and SHALL not fall back to omitted CEX detail when that repository or method is missing.
- AC20. WHEN Token Case or Search Inspect builds any token dossier THEN system SHALL require `latest_market_tick` and SHALL not fall back to `market_live.status = "missing"` when that repository method is missing.
- AC21. WHEN Pulse dirty-trigger admission evaluates a claimed target THEN system SHALL require job, edge-state, recent-failure, pending-count, and queue-depth repository methods and SHALL fail/retry the dirty trigger instead of falling back to empty control-plane state when a method is missing.
- AC22. WHEN `TokenProfileCurrentWorker` projects claimed profile targets THEN system SHALL require `RepositorySession.source_query` and SHALL fail/retry the dirty target instead of constructing `TokenProfileSourceQuery(repos.conn)` when that session contract is missing.
- AC23. WHEN `NotificationWorker` writes notification rows and external delivery rows THEN system SHALL require worker-session `unit_of_work` and SHALL fail before writes instead of falling back to `nullcontext` or manual commit when that session contract is missing.
- AC24. WHEN macrodata bundle import writes macro observations, import runs, and projection dirty targets THEN system SHALL require `RepositorySession.unit_of_work` and `require_transaction` and SHALL fail before writes instead of falling back to `conn.transaction()` when that session contract is missing.
- AC25. WHEN `PulseCandidateJobService` records Pulse agent execution, deterministic eval, candidate/playbook/admission updates, or job terminal state THEN system SHALL require `RepositorySession.transaction` and SHALL fail before writes instead of falling back to `nullcontext` or `conn.transaction()` when that session contract is missing.
- AC26. WHEN News page/source-quality projection workers claim dirty targets, write read models, enqueue downstream page dirty work, or mark dirty targets done/error THEN system SHALL require `RepositorySession.transaction` and SHALL fail before claim/write instead of falling back to `nullcontext` or `conn.transaction()` when that session contract is missing.
- AC27. WHEN `PulseCandidateWorker` claims dirty targets, writes admission/edge/public visibility/job enqueue state, or marks dirty targets done/error THEN system SHALL require `RepositorySession.transaction` and SHALL fail before claim/write instead of falling back to `conn.transaction()` when that session contract is missing.
- AC28. WHEN News fetch/process/brief writer workers reconcile sources, claim work, write facts, write agent admission/current brief state, enqueue projection dirty work, or mark failure state THEN system SHALL require `RepositorySession.transaction` and SHALL fail before reconcile/claim/write instead of falling back to `conn.transaction()` when that session contract is missing.
- AC29. WHEN EventAnchorBackfillWorker expires, reschedules, or fails stale event-anchor jobs or marks matching enriched event lifecycle terminal THEN system SHALL require worker-session `unit_of_work` and SHALL fail before cleanup writes instead of falling back to manual commit when that session contract is missing.
- AC30. WHEN TokenCaptureTierWorker claims token-capture-tier dirty targets, writes tier rows/demotions, or marks dirty targets done THEN system SHALL require `RepositorySession.transaction` and SHALL fail before claim/write instead of using manual commit or `commit=True` compatibility when that session contract is missing.
- AC31. WHEN EventAnchorBackfillJobRepository expires stale jobs or terminalizes claimed jobs THEN system SHALL require connection `transaction` and SHALL fail before job/terminal-ledger writes instead of falling back to `nullcontext` when that connection contract is missing.
- AC32. WHEN Queue Terminal resolves an operator action over a terminal event THEN system SHALL require connection `transaction` and SHALL fail before `SELECT ... FOR UPDATE` or operator-action writes instead of falling back to `nullcontext` or manual commit when that connection contract is missing.
- AC33. WHEN DiscoveryRepository terminalizes claimed lookup rows THEN system SHALL require connection `transaction` and SHALL fail before deleting `token_discovery_dirty_lookup_keys` or writing terminal-ledger rows instead of falling back to `nullcontext` or manual commit when that connection contract is missing.
- AC34. WHEN NewsProjectionDirtyTargetRepository terminalizes claimed projection dirty targets THEN system SHALL require connection `transaction` and SHALL fail before deleting `news_projection_dirty_targets` or writing terminal-ledger rows instead of falling back to `nullcontext` or manual commit when that connection contract is missing.
- AC35. WHEN ops projection dirty repair runs with `--execute` THEN system SHALL require connection `transaction` and SHALL fail before repair scans or dirty-target enqueue instead of falling back to `nullcontext` when that connection contract is missing; dry-run SHALL remain read-only.
- AC36. WHEN PulseJobsRepository terminalizes stale/exhausted jobs or marks failed/timeout jobs dead THEN system SHALL require connection `transaction` and SHALL fail before updating `pulse_agent_jobs` or writing terminal-ledger rows instead of falling back to `nullcontext` or manual commit when that connection contract is missing.
- AC37. WHEN PulseAdmissionRepository claims admission or suppression for a Pulse edge THEN system SHALL require connection `transaction` and SHALL fail before updating `pulse_candidate_edge_state`, locking/updating budget rows, or writing admission state instead of falling back to `nullcontext` when that connection contract is missing.
- AC38. WHEN MacroIntelRepository refreshes changed observation-series current rows THEN system SHALL require connection `transaction` and SHALL fail before deleting/inserting `macro_observation_series_rows` or updating `macro_observation_series_publication_state` instead of falling back to `nullcontext` when that connection contract is missing.
- AC39. WHEN PulseJobsRepository owns a commit for job enqueue, success marking, running-job release, or stale agent-run cleanup THEN system SHALL require connection `transaction` and SHALL fail before job/run SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC40. WHEN Pulse agent write repositories own a commit for agent runs, run steps, eval versions/cases/results, evidence packets, candidate rows, playbook rows, or ordinary admission edge/budget mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC41. WHEN PulseTriggerDirtyTargetRepository owns a commit for enqueue, due-claim, done, error, or reschedule mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC42. WHEN NewsProjectionDirtyTargetRepository owns a commit for enqueue, due-claim, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC43. WHEN TokenRadarSourceDirtyEventRepository owns a commit for enqueue, due-claim, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC44. WHEN TokenRadarDirtyTargetRepository owns a commit for target enqueue, market enqueue, due-claim, recent-resolved catch-up enqueue, market-current enqueue, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC45. WHEN MarketTickCurrentDirtyTargetRepository owns a commit for enqueue, due-claim, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC46. WHEN TokenProfileCurrentDirtyTargetRepository owns a commit for enqueue, due-claim, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC47. WHEN TokenImageSourceDirtyTargetRepository owns a commit for enqueue, due-claim, done, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC48. WHEN AssetProfileRefreshTargetRepository owns a commit for enqueue, due-claim, reschedule, or error mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC49. WHEN TokenCaptureTierDirtyTargetRepository owns a commit for rank-set enqueue, due-claim, or done mutations THEN system SHALL require connection `transaction` and SHALL fail before SQL instead of falling back to manual `self.conn.commit()` when that connection contract is missing.
- AC50. WHEN TokenRadarProjection publishes a rank set THEN system SHALL require callable connection `transaction` and SHALL fail before current-row publication side effects instead of using optional transaction probing or falling through to non-contract `TypeError` when that connection contract is malformed.
- AC51. WHEN EventAnchorBackfillJobRepository terminalizes job rows or writes terminal ledger evidence THEN system SHALL require callable connection `transaction` and SHALL fail before terminal SQL instead of using optional transaction probing when that connection contract is malformed.
- AC52. WHEN WakeBus emits a PostgreSQL wake hint or WakeWaiter registers `LISTEN` channels THEN system SHALL require callable wake-pool `commit` support, and WakeWaiter SHALL require callable `notifies` support, instead of silently treating missing connection methods as successful no-commit or local-wait behavior.
- AC53. WHEN ResolutionRefreshWorker marks lookup running, persists provider results, finishes/fails lookups, or completes lookup claims THEN system SHALL require `RepositorySession.transaction` and SHALL fail before provider fetch or state writes when that session contract is missing, instead of using manual `repos.conn.commit()` or raw connection transaction compatibility.
- AC54. WHEN NotificationDeliveryWorker claims delivery work, handles local delivery validation, completes log delivery, or records external push success/failure THEN system SHALL require `RepositorySession.transaction`, SHALL pass repository delivery writes through caller-owned `commit=False`, and SHALL keep Apprise/PushDeer IO outside DB transactions instead of using worker `.conn.commit()` or repository-owned manual commit on the worker path.
- AC55. WHEN token intent rebuild or token resolution reprocess rewrites token evidence/intents, lookup keys, resolution rows, discovery lookup dirty rows, identity evidence, or Token Radar source-dirty rows THEN system SHALL require `RepositorySession.transaction` and SHALL fail before writes when that session contract is missing, and `TokenIntentResolver` SHALL expose no direct commit flag or `resolutions.conn.commit()` compatibility.
- AC56. WHEN MacroViewProjectionWorker processes a macro projection dirty target THEN system SHALL require `RepositorySession.transaction` before claim, SHALL write observation-series rows, snapshot rows, and dirty-target done state through caller-owned `commit=False` inside that session transaction, SHALL mark dirty-target error without committing partial projection writes on failure, and SHALL emit `macro_view_snapshot_updated` only after the transaction exits.
- AC57. WHEN TokenRadarProjection processes claimed source-event or target dirty work THEN system SHALL require a callable connection `transaction` before dirty queue claim/processing SQL, SHALL keep source-edge writes, target-feature writes/deletes, rank publication attempts, and dirty done/error terminalization inside that transaction with caller-owned `commit=False`, and SHALL not retain worker/service `commit=True` fragments in the processing chain.
- AC58. WHEN AccountQualityBackfillService replays upstream facts into account profile/stat/snapshot read models THEN system SHALL require a callable connection `transaction` before backfill reads or writes, SHALL keep profile/stat/snapshot writes caller-owned with `commit=False` inside that transaction, and SHALL not retain naked `self.repository.conn.commit()` or optional transaction fallback in the service.
- AC59. WHEN Asset Market route/profile/symbol sync services execute DB writes after provider reads THEN system SHALL require a callable connection `transaction` before registry/profile writes, SHALL keep provider/client reads outside that transaction, SHALL use caller-owned `commit=False` writes inside it, and SHALL not retain naked `*.conn.commit()` or optional transaction fallback in those services.
- AC60. WHEN CLI ops execute commands mutate dirty queues, News repair state, or GMGN directory rows THEN system SHALL require a callable connection `transaction`, SHALL use caller-owned `commit=False` inside it, SHALL keep dry-run paths read-only and GMGN provider iteration outside DB transactions, and SHALL not retain `commit=True`, naked `.conn.commit()`, `nullcontext`, or optional transaction fallback in `ops.py`.
- AC61. WHEN a domain worker has committed work that should emit a wake hint and a wake object was injected THEN system SHALL call the required `notify_*` or `wake()` method directly, SHALL allow missing wake objects to mean "no low-latency hint", and SHALL not silently swallow malformed injected wake objects through optional method probing.
- AC62. WHEN `WorkerBase` receives an injected `wake_waiter` THEN stop/wait/close lifecycle code SHALL call `wake()`, `async_wait(...)`, and `close()` directly, SHALL allow a missing waiter to mean local interval sleep only, and SHALL not silently fall back when the injected waiter is malformed.
- AC63. WHEN CEX Market Intel publishes OI board rows, publication state, detail snapshots, derivative series, or attempt failure/skipped state THEN worker paths SHALL use `RepositorySession.transaction` with caller-owned `commit=False`, repository-owned commits SHALL require callable connection `transaction` before SQL, and the repositories SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC64. WHEN `NarrativeAdmissionDirtyTargetRepository` owns a commit for enqueue, due-claim, done, error, or reschedule mutations THEN system SHALL require callable connection `transaction` before `narrative_admission_dirty_targets` SQL, SHALL keep worker writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC65. WHEN `NarrativeRepository` owns a commit for `narrative_admissions` upsert or stale-target delete mutations THEN system SHALL require callable connection `transaction` before serving-row SQL, SHALL keep worker writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain `_commit_if_available`, naked `self.conn.commit()`, or optional commit probing.
- AC66. WHEN `TokenProfileCurrentRepository` owns a commit for `token_profile_current` upsert mutations THEN system SHALL require callable connection `transaction` before serving-row SQL, SHALL keep worker writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC67. WHEN `TokenImageAssetRepository` owns a commit for `token_image_assets` pending, ready, error, or unsupported lifecycle mutations THEN system SHALL require callable connection `transaction` before image-row SQL, SHALL keep TokenImageMirror terminal image writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC68. WHEN `IdentityEvidenceRepository` owns a commit for registry asset, identity evidence, or current identity mutations THEN system SHALL require callable connection `transaction` before registry/identity SQL, SHALL keep ingest/reprocess/refresh writes caller-owned with `commit=False` inside their outer transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC69. WHEN `RegistryRepository` owns a commit for registry asset, CEX token, price-feed, US equity symbol upsert, or US equity symbol deactivation mutations THEN system SHALL require callable connection `transaction` before registry/route/feed/symbol SQL, SHALL keep worker/service writes caller-owned with `commit=False` inside their outer transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC70. WHEN `DiscoveryRepository` owns a commit for lookup-key enqueue, due-claim, done, reschedule, start, finish, or fail mutations THEN system SHALL require callable connection `transaction` before discovery queue/result SQL, SHALL keep worker/reprocess writes caller-owned with `commit=False` inside their outer transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC71. WHEN `AssetProfileRepository` owns a commit for ready-profile or status mutations THEN system SHALL require callable connection `transaction` before `asset_profiles` source-cache SQL, SHALL keep `asset_profile_refresh` worker service writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC72. WHEN `CexTokenProfileRepository` owns a commit for ready-profile mutations THEN system SHALL require callable connection `transaction` before `cex_token_profiles` source-cache SQL, SHALL keep `sync_cex_token_profiles` writes caller-owned with `commit=False` inside its service transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC73. WHEN token fact repositories own commits for token evidence, token intents/evidence links, lookup-key replacement, or intent resolution mutations THEN system SHALL require callable connection `transaction` before fact SQL, SHALL keep ingest/rebuild/reprocess writes caller-owned with `commit=False` inside their outer transaction, SHALL enter the transaction before `pg_advisory_xact_lock`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC74. WHEN Queue Ops resolves a terminal retry transition THEN system SHALL require formal `signals.conn` plus the target retry repository/method contract before requeueing discovery lookup, event-anchor job, or Pulse agent job state, SHALL roll back the terminal action when the repository contract is absent, and SHALL not retain optional repository or method probing.
- AC75. WHEN TokenRadarRepository owns a commit for current generation publication, target-feature cache mutation, first-seen update, or publication failure state THEN system SHALL require callable connection `transaction` before SQL, SHALL enter the transaction before `pg_advisory_xact_lock`, SHALL keep worker projection writes caller-owned with `commit=False` inside the projection transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC76. WHEN EvidenceRepository or EntityRepository owns a commit for `raw_frames` input observations or `event_entities` fact-edge writes THEN system SHALL require callable connection `transaction` before SQL, SHALL keep full ingest event/entity writes caller-owned with `commit=False` inside `EvidenceRepository.unit_of_work`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC77. WHEN ProjectionRepository owns a commit for projection offsets, run ledger rows, stale-running cleanup, dirty-range enqueue, or dirty-range claim mutations THEN system SHALL require callable connection `transaction` before SQL, SHALL keep Token Radar publication control-plane writes caller-owned with `commit=False` inside the explicit projection transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC78. WHEN TokenRadarRankSourceRepository owns a commit for rank-source edge population by event, rank-source edge population by target, or rank-source edge pruning THEN system SHALL require callable connection `transaction` before `token_radar_rank_source_events` SQL, SHALL keep Token Radar dirty projection edge writes caller-owned with `commit=False` inside the explicit projection transaction, and SHALL not retain query-owned commit behavior, naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC79. WHEN TokenFactorEvaluationRepository owns a commit for a score-evaluation single upsert or batch upsert THEN system SHALL require callable connection `transaction` before `token_score_evaluations` SQL, SHALL keep per-row batch writes caller-owned with `commit=False` inside the repository transaction, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC80. WHEN SignalRepository owns a commit for a watched-account token alert insert THEN system SHALL require callable connection `transaction` before `account_token_alerts` SQL, SHALL keep ingest alert writes caller-owned with `commit=False` inside `EvidenceRepository.unit_of_work`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC81. WHEN AccountQualityRepository owns a commit for profile, directory entry, token call stat, or quality snapshot writes THEN system SHALL require callable connection `transaction` before SQL, SHALL keep AccountQualityBackfillService and GMGN directory sync writes caller-owned with `commit=False`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC82. WHEN NotificationRepository owns a commit for notification insert/aggregation, read-marker writes, delivery enqueue, or failed/dead delivery requeue THEN system SHALL require callable connection `transaction` before SQL, SHALL keep NotificationWorker writes caller-owned with `commit=False` inside worker-session `unit_of_work`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC83. WHEN NewsRepository owns a commit for source reconcile/claim, fetch run state, provider item/canonical item writes, deterministic item facts, agent run/current brief writes, source-quality rows, or page rows THEN system SHALL require callable connection `transaction` before SQL, SHALL keep News worker writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, method-local autocommit branches, `nullcontext`, or optional transaction probing.
- AC84. WHEN MacroIntelRepository owns a commit for projection dirty-target claim, done, or error mutations THEN system SHALL require callable connection `transaction` before SQL, SHALL keep MacroViewProjectionWorker writes caller-owned with `commit=False` inside `RepositorySession.transaction`, and SHALL not retain naked `self.conn.commit()`, `nullcontext`, or optional transaction probing.
- AC85. WHEN TokenRadarProjection enqueues downstream dirty targets after rank changes THEN system SHALL call formal repository-session dirty-target repositories directly for Pulse trigger, Narrative Admission, Token Profile Current, and Token Capture Tier work, and SHALL not retain optional `getattr(..., None)` repository probes or `if repo is None` compatibility branches.
- AC86. WHEN PulseEvidenceBuilder constructs a sealed evidence packet THEN system SHALL call formal evidence source repository methods directly for source events, enriched events, market facts, identity facts, and current discussion digest, and SHALL not retain optional method probes or empty-evidence compatibility defaults for missing repository contracts.
- AC87. WHEN SignalPulseService builds public health THEN system SHALL call formal `repository.freshness_health(...)` directly, SHALL fail missing method support as a repository/session wiring error, and SHALL not inspect `repository.conn`, instantiate `PulseFreshnessHealthService`, or return empty health for missing repository contracts.
- AC88. WHEN MacroSyncService enqueues due sync windows THEN system SHALL call formal `repos.macro_intel.macro_sync_queue_summary(...)` directly for queue notes/status, SHALL fail missing method support as repository/session wiring error, and SHALL not retain `_call_queue_summary`, optional method probes, or empty-summary defaults.
- AC89. WHEN Asset Market Binance route sync builds dry-run or execute summaries THEN system SHALL call formal `registry.binance_usdt_perp_sync_plan_counts(...)` directly for persisted CEX route/feed deltas, SHALL fail missing method support as repository wiring error, and SHALL not retain `_sync_plan_counts`, optional method probes, or input-length plan estimates.
- AC90. WHEN WorkerScheduler evaluates worker startability, liveness, or status payloads THEN system SHALL call worker `status_payload()` directly, SHALL fail missing/raising/non-object hooks as runtime wiring errors, and SHALL not infer worker state from partial attributes after swallowing status hook failures.
- AC91. WHEN API dependency helpers evaluate worker liveness or return a route-local worker object THEN system SHALL read the scheduler's canonical worker map and direct scheduler/worker `status_payload()` contracts, SHALL fail missing/raising/non-object hooks as runtime wiring errors, and SHALL not probe optional runtime fields, swallow hook errors, or unwrap ad-hoc worker aliases.
- AC92. WHEN collector bootstrap constructs `IngestService` THEN system SHALL read formal `RepositorySession` repositories directly for token evidence, token intents, intent resolutions, discovery, market ticks, enriched events, event-anchor jobs, and Token Radar source-dirty events; `IngestService` SHALL fail missing repositories as runtime wiring errors and SHALL not construct repository fallbacks from `evidence.conn` or retain `token_radar_dirty_targets` ingest compatibility parameters.
- AC93. WHEN WorkerScheduler builds unhealthy reasons THEN system SHALL derive unavailable reason, last error, and hard-timeout details from the worker `status_payload()` mapping already used for liveness, and SHALL not read direct worker attributes for those reason details.
- AC94. WHEN stream provider state is needed by worker degraded notes, readiness, ops diagnostics, or provider adapters THEN system SHALL call configured providers' `connection_state_payload()` contract directly, SHALL surface missing or non-dict hooks as failed provider state, and SHALL not retain optional hook probing or configured/disconnected fallbacks for configured providers.
- AC95. WHEN `/api/status` or ops diagnostics reports agent execution status THEN system SHALL read `runtime.agent_execution_gateway` directly, SHALL call `gateway.status_snapshot()` directly for non-null gateways, SHALL treat non-null malformed gateways as unavailable runtime wiring, and SHALL not read `runtime.providers.agent_execution_gateway`.
- AC96. WHEN `WorkerScheduler.stop()` closes runtime database resources THEN system SHALL call formal `db.aclose()` / `DBPoolBundle.aclose()` directly, SHALL treat missing `db.aclose()` as runtime wiring failure, and SHALL not close individual pool attributes as fallback.
- AC97. WHEN `bootstrap(...)` fails after creating the DB pool bundle THEN system SHALL call formal `db.aclose()` / `DBPoolBundle.aclose()` through the startup cleanup path, SHALL record cleanup failure on the original startup error, and SHALL not close individual pool attributes as fallback.
- AC98. WHEN WakeBus emits a PostgreSQL wake hint THEN system SHALL acquire a wake connection through the formal connection context returned by the wake-pool factory, SHALL require callable connection `commit`, and SHALL not execute `pg_notify` through a raw-connection fallback when the factory lacks `__enter__`.
- AC99. WHEN `WorkerBase` closes a single-writer advisory lock connection THEN system SHALL call the formal advisory lock connection `release()` contract directly, SHALL fail malformed lock objects as `worker_advisory_lock_release_required`, and SHALL not fall back to `close()` or optional release probing.
- AC100. WHEN CLI ops one-shot worker commands close their DB bundle or release an acquired advisory lock THEN system SHALL call formal `db.aclose()` and advisory lock `release()` directly, SHALL fail malformed handles as `ops_db_bundle_aclose_required` or `ops_advisory_lock_release_required`, and SHALL not close individual pool attributes or use `close()` fallback.
- AC101. WHEN `CollectorService` closes an owned upstream client THEN system SHALL call the formal `upstream_client.aclose()` contract, SHALL fail malformed clients as `collector_upstream_client_aclose_required`, and SHALL not fall back to `close()` or optional awaitable probing.
- AC102. WHEN runtime shutdown or bootstrap failure cleanup closes provider resources THEN system SHALL call formal root lifecycle methods directly, SHALL collect root cleanup errors, and SHALL not traverse provider object graphs or close provider-bundle `agent_execution_gateway` aliases.
- AC103. WHEN Pulse candidate or News fetch workers close owned providers THEN Pulse SHALL call `decision_client.aclose()` and fail close-only clients as `pulse_candidate_decision_client_aclose_required`, News fetch SHALL call synchronous `feed_client.close()` and fail awaitable close results as `news_fetch_feed_client_close_must_be_sync`, and neither worker SHALL probe fallback lifecycle shapes.
- AC104. WHEN asset-market or OKX provider wiring closes fallback/wrapped/partial providers THEN system SHALL call the provider `close()` contract directly, SHALL surface missing `close()` as cleanup failure evidence, and SHALL not skip malformed providers through optional close probing.
- AC105. WHEN `DBPoolBundle.create(...)` fails after partially creating pools THEN system SHALL call each partial pool's formal `close()` contract directly, SHALL record missing or failed close as cleanup notes on the original create exception, and SHALL not skip malformed pools through optional close probing or mask the original create failure with cleanup failure.
- AC106. WHEN DBPoolBundle discards a worker or advisory-lock connection after reset/unlock failure THEN system SHALL call the connection `close()` contract directly and return the closed connection through `pool.putconn(conn)`, SHALL treat missing `close()` as malformed connection wiring, and SHALL not use private pool `close_returns(...)` or optional `conn.close` probing as compatibility fallback.
- AC107. WHEN `MarketTickStreamWorker` finishes consuming a provider stream iterator THEN system SHALL call the iterator `aclose()` contract directly, SHALL surface a missing iterator close contract as degraded stream evidence, and SHALL not skip malformed iterators through optional async-close probing.
- AC108. WHEN `DBPoolBundle.aclose()` shuts down runtime pools THEN system SHALL call each pool's synchronous `close()` contract directly, SHALL fail awaitable or non-None close results as `db_pool_close_must_be_sync`, and SHALL not use `inspect.isawaitable(...)` or `await result` fallback for alternate pool lifecycle shapes.
- AC109. WHEN CLI ops one-shot asset-market workers finish or fail after wiring providers THEN system SHALL call formal `asset_market.aclose()` directly, SHALL fail malformed provider bundles as `ops_asset_market_providers_aclose_required`, and SHALL not enumerate `cex_market` / `dex_*` provider fields or use optional provider `close()` probing.
- AC110. WHEN `WorkerBase.aclose()` closes an injected wake waiter THEN system SHALL call `wake_waiter.close()` directly, SHALL fail awaitable or non-None close results as `worker_wake_waiter_close_must_be_sync`, and SHALL not use `inspect.isawaitable(...)` / `await result` fallback for alternate wake-waiter close shapes.
- AC111. WHEN `WorkerScheduler.stop()` stops workers and closes runtime DB resources THEN system SHALL `await worker.stop()`, `await worker.aclose()`, and `await self.db.aclose()` directly, SHALL fail synchronous or non-awaitable lifecycle hook results as malformed runtime wiring, and SHALL not use `_maybe_await(...)`, `inspect.isawaitable(...)`, or `await _maybe_await(...)` fallback for alternate lifecycle shapes.
- AC112. WHEN `LivePriceGateway` fans out a live market update THEN system SHALL await the configured `on_live_market_update(payload)` async publish contract directly, SHALL fail synchronous or non-awaitable callback results as malformed runtime wiring, and SHALL not use `inspect.isawaitable(...)` / conditional await fallback for alternate publish callback shapes.
- AC113. WHEN `DirectGmgnWebSocketClient` receives an upstream frame THEN system SHALL await the configured `on_frame(frame)` async collector contract directly, SHALL fail synchronous or non-awaitable callback results as malformed runtime wiring, and SHALL not use `inspect.isawaitable(...)` / conditional await fallback for alternate frame handler shapes.
- AC114. WHEN `AgentCapacityReservation.release()` releases lane/global/rate capacity THEN system SHALL call the configured `_release()` synchronous resource-release callback directly, SHALL fail awaitable or non-None release results as `agent_capacity_release_must_be_sync`, and SHALL not use `Awaitable` callback typing or `await result` fallback for alternate release shapes.
- AC115. WHEN `OpenNewsFeedClient` fetches REST pages THEN system SHALL await the configured `post_json(url, token=..., body=...)` async HTTP poster contract directly, SHALL fail synchronous or non-awaitable poster results as malformed provider wiring, and SHALL not use `inspect.isawaitable(...)` / conditional await fallback for alternate poster shapes.
- AC116. WHEN `postgres_health_check(...)` probes PostgreSQL THEN system SHALL call `conn.commit()` after successful probe SQL and `conn.rollback()` after probe failures through the formal connection contract, SHALL report malformed missing cleanup contracts as failed liveness payloads, and SHALL not use `hasattr(conn, "commit")` or `hasattr(conn, "rollback")` optional probes as compatibility fallback.
- AC117. WHEN `OpenNewsFeedClient.fetch(...)` bridges the async REST fetch into the synchronous worker thread THEN system SHALL pass a typed coroutine to `_run_rest_fetch(...)`, SHALL call `coro.close()` directly before raising the active-event-loop misuse error, and SHALL not accept arbitrary `Any` / close-probed awaitable shapes.
- AC118. WHEN `require_transaction(conn, operation=...)` verifies an inner write runs inside an active PostgreSQL transaction THEN system SHALL read `conn.info.transaction_status` directly, SHALL raise a transaction-status contract error for fake/malformed connections that omit that status, SHALL keep the existing idle-transaction `operation_requires_explicit_transaction` failure, and SHALL not return silently from missing `info` / missing `transaction_status` probes.
- AC119. WHEN `asset_profile_refresh` or `resolution_refresh` is enabled but its required Asset Market provider dependency is missing THEN worker construction SHALL return an `unavailable` worker with a redacted missing-provider reason, SHALL keep the worker `enabled` flag true for readiness/unhealthy-reason accounting, and SHALL not use `disabled_worker(...)` to hide the missing provider as operator intent.
- AC120. WHEN CEX Market Intel or News Intel worker factories access provider dependencies THEN system SHALL read `ctx.providers.cex_market_intel` and `ctx.providers.news_intel` directly as formal domain bundle roots, SHALL let missing roots fail as malformed runtime wiring, and SHALL reserve `unavailable_worker(...)` for missing concrete providers inside an existing domain bundle.
- AC121. WHEN `/readyz` or ops diagnostics reads provider status THEN system SHALL read `runtime.providers.asset_market` directly as a formal runtime domain bundle root, SHALL let a missing bundle fail as malformed runtime wiring, and SHALL reserve disabled/disconnected provider state for concrete `None` provider handles inside the existing bundle.
- AC122. WHEN ops diagnostics builds the collector section THEN system SHALL call `runtime.collector.status.to_dict()` and read `runtime.collector.upstream_client` directly, SHALL require the status payload to be a mapping, and SHALL not use optional collector/status/to_dict probes that hide malformed collector status wiring as empty diagnostics.
- AC123. WHEN ops diagnostics builds Asset Market provider health THEN system SHALL read `runtime.providers.asset_market.provider_health` directly as a formal bundle field, SHALL let missing provider-health support fail as malformed provider-bundle wiring, and SHALL not use optional `getattr(..., "provider_health", ())` fallback that hides malformed wiring as an empty provider inventory.
- AC124. WHEN Asset Market worker factories access provider dependencies THEN system SHALL read `cex_market`, `dex_quote_market`, `dex_profile_sources`, `dex_discovery_market`, and `stream_dex_market` directly from `ctx.providers.asset_market`, SHALL let missing fields fail as malformed provider-bundle wiring, and SHALL reserve `unavailable_worker(...)` for present concrete provider fields whose value is `None` or empty.
- AC125. WHEN CEX Market Intel or News Intel worker factories access provider dependencies THEN system SHALL read `oi_market`, `coinglass_derivatives`, `feed_client`, and `brief_provider` directly from their domain provider bundles, SHALL let missing fields fail as malformed provider-bundle wiring, and SHALL reserve `unavailable_worker(...)` for present concrete provider fields whose value is `None`.
- AC126. WHEN runtime status builds the News provider-contract payload THEN system SHALL read `runtime.settings.news_intel.sources` directly as the formal runtime settings contract, SHALL let missing News Intel settings fail as malformed runtime configuration, and SHALL not use nested optional `getattr(..., "news_intel", None)` / empty-source fallback.
- AC127. WHEN ops diagnostics builds config or watchlist sections THEN system SHALL read `runtime.settings` and its formal fields directly, SHALL let missing settings fail as malformed runtime configuration, and SHALL not use optional `getattr(runtime, "settings", None)` or field fallbacks that hide malformed runtime configuration as empty config or idle watchlist state.
- AC128. WHEN ops diagnostics builds queue summaries THEN system SHALL open `runtime.db.api_pool.connection()` directly as the formal diagnostics DB read contract, SHALL let missing DB/API pool/connection support fail as malformed runtime DB wiring, and SHALL not use optional DB/pool/connection probes or empty-list fallback that hides malformed runtime wiring as no queue state.
- AC129. WHEN worker status enriches manifest-owned queue health THEN system SHALL construct the connection context through `runtime.db.api_pool.connection()` directly before fallback handling, SHALL let missing DB/API pool/connection support fail as malformed runtime DB wiring, SHALL keep real context-enter/query failures as queue-health unavailable state, and SHALL not retain the old `missing_connection` error-code compatibility path.
- AC130. WHEN runtime readiness code is reviewed THEN system SHALL not retain `_notification_summary(...)`, SHALL not keep an unused `repos.notifications.summary(...)` readiness helper, and SHALL not keep a catch-all `except Exception: return {}` notification-summary fallback that future status surfaces could reuse.
- AC131. WHEN worker construction fills a missing worker with a disabled/intentionally-not-started/unavailable sentinel THEN system SHALL read `settings.workers.<name>` directly as the formal worker settings contract, SHALL let absent settings blocks fail as malformed runtime configuration, and SHALL not default absent worker settings to enabled or synthesize `SimpleNamespace(enabled=...)` settings.
- AC132. WHEN `DBPoolBundle` computes wake listener concurrency and wake pool size THEN system SHALL read `settings.workers` directly, SHALL iterate manifest-declared wake listeners, SHALL read each wake worker's `enabled`, `wakes_on`, and `concurrency` settings directly, and SHALL not treat missing worker settings shape as zero wake listener demand.
- AC133. WHEN `ops rebuild-market-tick-current` computes advisory lock keys or worker-session statement timeouts THEN system SHALL read `settings.workers.market_tick_current_projection` directly, SHALL let missing worker settings fail before `DBPoolBundle.create(...)`, and SHALL not use nested optional `getattr(..., SimpleNamespace())` or `_LockProbe` compatibility to synthesize defaults.
- AC134. WHEN CLI ops one-shot commands need an advisory lock key from a constructed worker THEN system SHALL call `worker._advisory_lock_key()` directly, SHALL fail workers missing that method as `ops_worker_advisory_lock_key_required`, and SHALL not fall back to `worker.SINGLE_WRITER_KEY` or class-name-based error shaping.
- AC135. WHEN Asset Market wiring creates a configured GMGN DEX provider THEN system SHALL require the concrete provider to expose `token_quotes(...)` and `token_profile(...)` directly, SHALL fail malformed providers as `asset_market_token_quotes_required` or `asset_market_token_profile_required`, and SHALL not use optional capability probes that hide malformed GMGN wiring by falling back to OKX quotes or omitting the GMGN profile source.
- AC136. WHEN CEX Market Intel provider wiring decides whether to construct CoinGlass enrichment THEN system SHALL read `settings.workers.cex_oi_radar_board.enabled` and `.coinglass_enrichment_limit` directly, SHALL let missing fields fail as malformed runtime configuration, and SHALL not synthesize enabled/default-zero behavior through `getattr(..., default)`.
- AC137. WHEN Asset Market wiring cleans up after a startup failure and an `OkxProviderBundle` object exists THEN system SHALL read `dex_discovery_market`, `dex_quote_market`, and `stream_dex_market` as formal bundle fields, SHALL record missing fields as cleanup failure notes on the original startup error while closing any readable providers, and SHALL not use optional `getattr(okx_bundle, ..., None)` probes that hide malformed bundle shape as absent providers.
- AC138. WHEN model-execution provider wiring computes the Pulse decision pipeline timeout THEN system SHALL read `settings.workers.agent_runtime.lanes["pulse.decision"].timeout_seconds` through the formal lane settings contract, SHALL let missing lanes or timeout fields fail as malformed runtime configuration, and SHALL not use provider-local 120-second fallback behavior.
- AC139. WHEN worker factory sentinel helpers must change `enabled` for disabled or intentionally-not-started status THEN system SHALL clone the formal Pydantic worker settings via `model_copy(update={"enabled": ...})`, SHALL fail non-model settings as `worker_settings_model_copy_required:<worker>`, and SHALL not dump arbitrary objects through `model_dump`, `__dict__`, `vars(...)`, or `SimpleNamespace(**...)` compatibility paths.
- AC140. WHEN `CollectorService` configures snapshot gate timing THEN system SHALL read `settings.snapshot_timeout_seconds` directly from the formal collector worker settings object, SHALL let missing timeout support fail as malformed worker settings, and SHALL not use `getattr(settings, "snapshot_timeout_seconds", 0.5)` or any service-local timeout default.
- AC141. WHEN `MarketTickPollWorker` is constructed THEN system SHALL require the formal `settings.workers.market_tick_poll` object, Asset Market provider bundle, and DB pool bundle, SHALL read `settings.batch_size` and `settings.concurrency` directly, and SHALL not synthesize settings/provider bundles or accept legacy `dex_quote_market`, `cex_market`, `batch_size`, `interval_seconds`, `wake_bus`, or `db` constructor compatibility paths.
- AC142. WHEN CLI ops one-shot worker commands override worker settings such as `batch_size` or `reprocess_limit` THEN system SHALL clone the formal Pydantic worker settings via `model_copy(update=...)`, SHALL fail non-model settings as `ops_worker_settings_model_copy_required`, and SHALL not dump arbitrary objects through `model_dump`, `vars(...)`, `__dict__`, or `SimpleNamespace(**...)` compatibility paths.
- AC143. WHEN `WorkerBase` reads core runtime settings THEN system SHALL read `settings.enabled`, `settings.interval_seconds`, and `settings.backoff.base_ms/max_ms` directly from the formal `PerWorkerSettings` object, SHALL let missing support fail as malformed worker settings, and SHALL not use base-class fallback defaults for enabled state, interval cadence, or retry backoff.
- AC144. WHEN `TokenCaptureTierWorker` is constructed or claims capture-tier dirty targets THEN system SHALL require the formal `settings.workers.token_capture_tier` object and DB pool bundle, SHALL read `settings.batch_size`, `settings.ws_limit`, `settings.poll_limit`, and `settings.lease_ms` directly, and SHALL not synthesize settings or accept legacy `db`, `batch_size`, `ws_limit`, `poll_limit`, or `interval_seconds` constructor compatibility paths.
- AC145. WHEN `EventAnchorBackfillWorker` is constructed or opens worker sessions THEN system SHALL require the formal `settings.workers.event_anchor_backfill` object, DB pool bundle, and Asset Market provider bundle unless an explicit capture service is injected, SHALL read `settings.batch_size`, `settings.concurrency`, `settings.max_attempts`, `settings.lease_ms`, `settings.min_age_ms`, `settings.active_window_ms`, `settings.max_anchor_lag_ms`, and `settings.statement_timeout_seconds` directly, and SHALL not synthesize settings or accept legacy `db`, `wake_bus`, `dex_quote_market`, `cex_market`, `batch_size`, `concurrency`, `min_age_ms`, `active_window_ms`, `max_anchor_lag_ms`, or `interval_seconds` constructor compatibility paths.
- AC146. WHEN `TokenProfileCurrentWorker` opens worker sessions or rebuilds current profile rows THEN system SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, and `settings.retry_ms` directly from the formal `settings.workers.token_profile_current` object, SHALL define `retry_ms` in the formal worker settings schema, SHALL require `rebuild_token_profile_current_once(...)` callers to pass limit, lease owner, lease, and retry arguments explicitly, and SHALL not retain worker-local `DEFAULT_LEASE_MS` / `DEFAULT_RETRY_MS`, `getattr(self.settings, ..., default)` settings fallbacks, or helper parameter defaults.
- AC147. WHEN `MarketTickCurrentProjectionWorker` claims market-current dirty targets, opens projection/error sessions, or schedules dirty-target retry THEN system SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, and `settings.retry_ms` directly from the formal `settings.workers.market_tick_current_projection` object, and SHALL not retain worker-local retry defaults, hard-coded lease/batch fallback values, or `getattr(self.settings, ..., default)` settings probes.
- AC148. WHEN `TokenImageMirrorWorker` claims image-source dirty targets, opens image terminal-write sessions, or schedules dirty-source retry THEN system SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, and `settings.retry_ms` directly from the formal `settings.workers.token_image_mirror` object, SHALL define `retry_ms` in the formal worker settings schema, and SHALL not retain worker-local `DEFAULT_LEASE_MS` / `DEFAULT_RETRY_MS`, hard-coded statement-timeout/batch fallbacks, or `getattr(self.settings, ..., default)` settings probes.
- AC149. WHEN `AssetProfileRefreshWorker` claims provider-scoped profile refresh targets, opens profile write/reschedule sessions, or schedules provider-block retry THEN system SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, and `settings.provider_retry_ms` directly from the formal `settings.workers.asset_profile_refresh` object, SHALL define `provider_retry_ms` in the formal worker settings schema, and SHALL not retain worker-local `DEFAULT_LEASE_MS` / `DEFAULT_PROVIDER_RETRY_MS`, hard-coded batch fallback values, or `getattr(self.settings, ..., default)` settings probes.
- AC150. WHEN `MarketTickStreamWorker` is constructed or bounds a Tier 1 stream cycle THEN system SHALL require the formal `settings.workers.market_tick_stream` object, DB pool bundle, configured stream provider, and wake emitter from the worker factory, SHALL read `settings.subscription_limit` and `settings.stream_cycle_seconds` directly, SHALL define `stream_cycle_seconds` in the formal worker settings schema, and SHALL not retain `SimpleNamespace` settings synthesis, `db` / `wake_bus` aliases, constructor `subscription_limit`, `interval_seconds`, or `stream_cycle_seconds` overrides, `DEFAULT_SUBSCRIPTION_LIMIT` / `DEFAULT_STREAM_CYCLE_SECONDS`, or settings `__dict__` compatibility paths.
- AC151. WHEN `ResolutionRefreshWorker` is constructed, claims discovery lookup keys, reprocesses affected intents, or emits resolution wake hints THEN system SHALL require the formal `settings.workers.resolution_refresh` object and configured discovery provider, SHALL read `settings.chain_ids`, `settings.max_attempts`, `settings.batch_size`, and `settings.reprocess_limit` directly, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `chain_ids`, unused `dex_quote_market`, `wake_bus` aliases, `DEFAULT_DISCOVERY_LIMIT` / `DEFAULT_REPROCESS_LIMIT` fallback values, or `getattr(settings, ..., default)` settings probes.
- AC152. WHEN `LivePriceGateway` is constructed, selects live targets, or loads latest market ticks for WebSocket fan-out THEN system SHALL require the formal `settings.workers.live_price_gateway` object and DB pool bundle, SHALL read `settings.target_limit` and `settings.target_ttl_seconds` directly, SHALL define both fields in the formal worker settings schema/default workers YAML, and SHALL not retain `SimpleNamespace` settings synthesis, constructor `providers` or `interval_seconds` compatibility paths, `DEFAULT_LIVE_TARGET_LIMIT` / `DEFAULT_LIVE_TARGET_TTL_SECONDS`, or duplicate factory field passing.
- AC153. WHEN `NewsPageProjectionWorker` opens worker sessions, claims page projection dirty targets, or schedules dirty-target retry THEN system SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, and `settings.retry_ms` directly from the formal `settings.workers.news_page_projection` object, SHALL define those fields in the formal worker settings schema/default workers YAML, and SHALL not retain `getattr(self.settings, ..., default)` probes or hard-coded batch/lease/retry fallback values in runtime code.
- AC154. WHEN `MacroViewProjectionWorker` is constructed, opens worker sessions, claims macro projection dirty targets, refreshes observation history, emits snapshot wake hints, or schedules dirty-target retry THEN system SHALL require the formal `settings.workers.macro_view_projection` object and DB pool bundle, SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, `settings.retry_ms`, `settings.lookback_days`, and `settings.limit_per_series` directly, SHALL define `lease_ms` and `retry_ms` in the formal worker settings schema/default workers YAML, SHALL enforce macro history lower bounds in settings schema, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs` compatibility paths, `MACRO_VIEW_HISTORY_*` runtime fallback constants, `getattr(self.settings, ..., default)` settings probes, or hard-coded `limit=1` claim behavior.
- AC155. WHEN `NewsSourceQualityProjectionWorker` is constructed, opens worker sessions, claims source-quality dirty targets, expands configured source-quality windows, emits page-dirty wake hints, or schedules dirty-target retry THEN system SHALL require the formal `settings.workers.news_source_quality_projection` object and DB pool bundle, SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, `settings.retry_ms`, and `settings.windows` directly, SHALL define `lease_ms`, `retry_ms`, and `statement_timeout_seconds` in the formal worker settings schema/default workers YAML, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs` compatibility paths, `getattr(self.settings, ..., default)` settings probes, or hard-coded batch/lease/retry/window fallback values in runtime code.
- AC156. WHEN `NewsItemProcessWorker` is constructed, opens worker sessions, claims unprocessed news items, marks retryable/terminal failures, or emits processed-item wake hints THEN system SHALL require the formal `settings.workers.news_item_process` object and DB pool bundle, SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, `settings.max_attempts`, and `settings.retry_delay_ms` directly, SHALL define `batch_size`, `lease_ms`, `max_attempts`, and `statement_timeout_seconds` in the formal worker settings schema/default workers YAML, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs` compatibility paths, `getattr(self.settings, ..., default)` settings probes, or hard-coded batch/lease/max-attempt/retry fallback values in runtime code.
- AC157. WHEN `NewsItemBriefWorker` is constructed, opens worker sessions, claims item-brief dirty targets, handles provider backpressure/no-start paths, marks retryable dirty-target failures, or emits brief-updated wake hints THEN system SHALL require the formal `settings.workers.news_item_brief` object, DB pool bundle, and provider, SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, `settings.lease_ms`, `settings.retry_ms`, and `settings.backpressure_cooldown_ms` directly, SHALL define `lease_ms`, `retry_ms`, and `statement_timeout_seconds` in the formal worker settings schema/default workers YAML, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs`/optional-provider compatibility paths, `getattr(self.settings, ..., default)` settings probes, or hard-coded batch/lease/retry/backpressure fallback values in runtime code.
- AC158. WHEN `NewsPageProjectionWorker` is constructed or wired by the News worker factory THEN system SHALL require the formal `settings.workers.news_page_projection` object and DB pool bundle, SHALL keep session timeout, claim batch, lease, and retry budgets as direct formal settings reads, and SHALL not retain constructor `wake_bus`/`**kwargs` compatibility paths or factory `wake_bus=ctx.wake_bus` injection for a projection that emits no downstream wake.
- AC159. WHEN `NewsFetchWorker` is constructed, reconciles configured sources, opens worker sessions, claims due sources, fetches provider observations, persists news facts, or emits item/page dirty wake hints THEN system SHALL require the formal `settings.workers.news_fetch` object, DB pool bundle, News Intel settings, and feed client, SHALL read `settings.statement_timeout_seconds`, `settings.batch_size`, and `news_settings.sources` directly, SHALL define `statement_timeout_seconds` in the formal worker settings schema/default workers YAML, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs`/optional-feed-client compatibility paths, `getattr(self.settings, ..., default)` or `getattr(self.news_settings, ...)` settings probes, or hard-coded batch fallback values in runtime code.
- AC160. WHEN `MacroSyncWorker` or `MacroSyncService` is constructed, enqueues due sync windows, claims macro sync windows, opens worker sessions, retries failed windows, drains bounded windows per cycle, or emits imported-observation wake hints THEN system SHALL require the formal `settings.workers.macro_sync` object, DB/repository-session contract, and root settings, SHALL read source/bundle identity, bootstrap/window cadence, max attempts, lease, retry delay, statement timeout, and batch size directly from formal worker settings, SHALL define `batch_size` in the formal worker settings schema/default workers YAML, SHALL receive the wake emitter through `wake_emitter`, and SHALL not retain constructor `wake_bus`/`**kwargs` compatibility paths, `_sync_settings` or bare-settings fallback, `getattr(..., default)` execution-budget probes, or hard-coded source/bundle/lease/retry/timeout defaults in runtime code.
- AC161. WHEN `CexOiRadarBoardWorker` is constructed, selects the Binance perp universe, opens worker sessions, builds the CEX OI board, enriches CoinGlass details, publishes current board/detail rows, or records attempt failures THEN system SHALL require the formal `settings.workers.cex_oi_radar_board` object, DB bundle, telemetry, and concrete OI market provider, SHALL read `period`, `universe_limit`, `batch_size`, `statement_timeout_seconds`, `coinglass_enrichment_limit`, and `coinglass_level_limit` directly from formal worker settings, SHALL let the worker factory represent missing OI provider state as an unavailable worker, and SHALL not retain constructor `**kwargs`, optional OI provider worker execution paths, `getattr(self.settings, ..., default)` settings probes, or hard-coded period/universe/CoinGlass/batch/timeout defaults in runtime code.
- AC162. WHEN `NotificationWorker` or `NotificationDeliveryWorker` is constructed, opens worker sessions, limits per-cycle notification creation/delivery processing, enqueues/requeues external deliveries, claims pending deliveries, or records delivery completion/failure THEN system SHALL require the formal `settings.workers.notification_rule` / `settings.workers.notification_delivery` objects and DB bundle, SHALL read `batch_size` and `statement_timeout_seconds` directly from formal worker settings, SHALL define `statement_timeout_seconds` in both formal worker settings schemas/default workers YAML, and SHALL not retain `getattr(settings, "batch_size", ...)`, `getattr(self.settings, "statement_timeout_seconds", ...)`, or hard-coded batch/timeout runtime fallback values.
- AC163. WHEN `MacroDailyBriefProjectionWorker` is constructed, opens worker sessions, reads the current macro view snapshot, or writes the stable `assets_today` daily brief row THEN system SHALL require the formal `settings.workers.macro_daily_brief_projection` object and DB bundle, SHALL read `statement_timeout_seconds` directly from formal worker settings, and SHALL not retain constructor `**kwargs`, `super().__init__(**kwargs)`, `getattr(self.settings, "statement_timeout_seconds", ...)`, or old wake alias compatibility paths in runtime code.
- AC164. WHEN `TokenRadarProjectionWorker` is constructed, selects projection windows/scopes/venues, schedules hot/cold work, claims dirty targets, opens worker sessions, or emits `token_radar_updated` wake hints THEN system SHALL require the formal `settings.workers.token_radar_projection` object and DB bundle, SHALL read `windows`, `scopes`, `venues`, `hot_windows`, `batch_size`, `cold_interval_seconds`, and `statement_timeout_seconds` directly from formal worker settings, SHALL receive downstream wake output through `wake_emitter`, and SHALL not retain worker-local default window/scope/hot-window tuples, `TOKEN_RADAR_VENUES` fallback, `getattr(settings, ..., default)` probes, `getattr(self.settings, "statement_timeout_seconds", ...)`, or old `wake_bus` constructor/factory/CLI compatibility paths.
- AC165. WHEN `NarrativeAdmissionWorker` is constructed, claims narrative admission dirty targets, opens worker sessions, computes deterministic admission thresholds, or schedules dirty-target retry THEN system SHALL require the formal `settings.workers.narrative_admission` object and DB bundle, SHALL read `admission_limit`, `source_limit`, `lease_ms`, `retry_ms`, `statement_timeout_seconds`, `hot_rank_limit`, and `min_rank_score` directly from formal worker settings, SHALL define lease/retry/statement-timeout fields in the formal settings schema/default workers YAML, SHALL remain wake-in only through `wake_waiter`, and SHALL not retain `lease_seconds` / `error_retry_seconds`, `getattr(..., default)` settings probes, statement-timeout fallback, or old `wake_bus` / `wake_emitter` constructor/factory compatibility paths.
- AC166. WHEN `PulseCandidateWorker` or `PulseCandidateJobService` is constructed, selects candidate windows/scopes, claims dirty triggers, limits enqueue/agent-job work, computes trigger/gate thresholds, opens worker sessions, or processes Pulse agent jobs THEN system SHALL require the formal `settings.workers.pulse_candidate` object, DB bundle, and decision client, SHALL read `windows`, `scopes`, `batch_size`, `max_agent_jobs_per_cycle`, `max_attempts`, `max_enqueues_per_cycle`, `max_pending_jobs_global`, `max_pending_jobs_per_window_scope`, trigger thresholds, gate thresholds, and `statement_timeout_seconds` directly from formal worker settings, SHALL define statement timeout in the formal settings schema/default workers YAML, and SHALL not retain worker-local window/scope defaults, `SIGNAL_PULSE_WINDOWS` fallback, `getattr(settings, ..., default)` probes, `getattr(self.settings, "statement_timeout_seconds", ...)`, or job-service statement-timeout compatibility paths.
- AC167. WHEN `WorkerBase` acquires a single-writer advisory lock for any worker declaring `SINGLE_WRITER_KEY` THEN system SHALL read the formal `settings.workers.<name>.advisory_lock_key` field through the worker settings object, SHALL fail missing or `None` lock settings as `worker_advisory_lock_key_required`, and SHALL not fall back to `SINGLE_WRITER_KEY` as a runtime lock-key source.
- AC168. WHEN `MacrodataBundleRunner` or `MacroSyncService` reports FRED key state, injects macrodata child-process secrets, or chooses the macrodata subprocess timeout THEN system SHALL read the formal root settings properties `macrodata_fred_api_key_env` and `macrodata_fred_api_key` plus `settings.workers.macro_sync.macrodata_timeout_seconds`, SHALL fail missing formal settings attributes as explicit runtime contract errors, and SHALL not probe nested `settings.providers.macrodata.*`, root-level `macrodata_timeout_seconds`, or hard-coded timeout compatibility fallback values.
- AC169. WHEN `MarketTickPollWorker` polls Tier 2 DEX/CEX market targets THEN system SHALL read `providers.dex_quote_market` and `providers.cex_market` directly from the formal Asset Market provider bundle, SHALL treat missing provider fields as malformed runtime wiring, SHALL keep present `None` field values as explicit unavailable concrete provider state, and SHALL not use `getattr(self.providers, ..., None)` optional-provider probes inside the worker.
- AC170. WHEN token resolution refresh or token intent rebuild helpers reprocess recent token facts THEN system SHALL require callers to pass window, limit, and projection-limit values explicitly, SHALL use `WINDOW_MS[window]` instead of fallback window lookup, SHALL expose the named `TOKEN_REPROCESS_WINDOW` policy for `ResolutionRefreshWorker`, and SHALL not retain `DEFAULT_REPROCESS_LIMIT`, `DEFAULT_REPROCESS_WINDOW`, or service-local default limit/window/projection-limit parameters.
- AC171. WHEN Pulse decision model-execution code exposes provider execution timeout to domain orchestration THEN system SHALL expose the timeout only through `LiteLLMPulseDecisionProvider` from the formal `workers.agent_runtime.lanes["pulse.decision"].timeout_seconds` lane settings, SHALL keep `LiteLLMPulseDecisionClient` free of `timeout_seconds` / `_DEFAULT_TIMEOUT_SECONDS` provider-budget surface, and SHALL not retain a client-local 120-second fallback that can bypass provider wiring.
- AC172. WHEN collector ingest enqueues `event_anchor_backfill_jobs` for pending event anchors THEN system SHALL pass `settings.workers.event_anchor_backfill.active_window_ms` explicitly from the composition root through `_PooledIngestStore`, `_ingest_service_for_repos`, and `IngestService`, SHALL treat missing active-window arguments as malformed bootstrap/test wiring, and SHALL not retain `DEFAULT_EVENT_ANCHOR_ACTIVE_WINDOW_MS`, `event_anchor_active_window_ms=300_000`, or ingest-layer active-window defaults.
- AC173. WHEN `NewsFetchWorker` claims due `news_sources` for provider fetch work THEN system SHALL read source-claim lease duration from formal `settings.workers.news_fetch.lease_ms`, SHALL pass `claim_lease_ms` explicitly to `NewsRepository.claim_due_sources(...)`, SHALL define `lease_ms` in the formal worker settings schema/default workers YAML, and SHALL not retain `_DEFAULT_SOURCE_CLAIM_LEASE_MS` or repository-local `claim_lease_ms` default parameters.
- AC174. WHEN Pulse stale running agent jobs are reclaimed or terminalized THEN system SHALL read stale-running timeout from formal `settings.workers.pulse_candidate.job_running_timeout_ms`, SHALL pass that policy into `PulseJobsRepository` at repository-session construction and into worker terminalization calls explicitly, SHALL define `job_running_timeout_ms` in the formal worker settings schema/default workers YAML, and SHALL not retain worker `getattr(pulse_jobs, "running_timeout_ms", ...)` fallback, `PulseJobsRepository` constructor defaults, or unused running-timeout state in other Pulse repositories.
- AC175. WHEN notification delivery stale running rows are reclaimed, terminalized, or claimed THEN system SHALL read running timeout and stale-running terminalization batch size from formal `settings.workers.notification_delivery.running_timeout_ms` and `stale_running_terminalization_batch_size`, SHALL pass both policies into `NotificationRepository` at repository-session construction, SHALL define both fields in the formal worker settings schema/default workers YAML, and SHALL not retain repository-local delivery timeout constants or constructor default parameters.
- AC176. WHEN `AccountQualityBackfillService` replays upstream facts into account-quality read models THEN system SHALL require callers to pass `limit` explicitly, SHALL keep the CLI `--limit` default at the command boundary, and SHALL not retain a service-local `limit` default inside the account-quality backfill service.
- AC177. WHEN `NotificationRuleEngine` evaluates Signal Pulse notification candidates THEN system SHALL read `window`, `scopes`, and `statuses` only from the validated `settings.notifications.rules.signal_pulse_candidate` rule, SHALL reject empty or unsupported query dimensions during notification settings validation, and SHALL not retain service-local `DEFAULT_SIGNAL_PULSE_*` constants or `rule.window/scopes/statuses or ...` compatibility defaults.
- AC178. WHEN `NotificationRuleEngine` limits candidate scans THEN system SHALL use `settings.notifications.candidate_limit` directly after settings-layer `ge=1` validation, and SHALL not retain service-local `DEFAULT_LIMIT`, `max(DEFAULT_LIMIT, ...)`, or `max(50, ...)` floors that override formal notification config.
- AC179. WHEN notification settings parse non-Signal rules (`watched_account_activity`, `watched_account_token_alert`, `news_high_signal`) THEN system SHALL reject Signal Pulse-only `window`, `scopes`, or `statuses` query fields for those rules, SHALL keep non-Signal rules to delivery settings only, and SHALL not silently load query fields that the rule engine ignores.
- AC180. WHEN `NotificationWorker` handles repository insert results THEN system SHALL consume the formal `NotificationInsertOutcome` contract directly through `outcome.row`, `outcome.created`, and `outcome.aggregated`, and SHALL not infer created/aggregated state from bare row dictionaries or retain `getattr(outcome, ..., default)` fallback shapes.
- AC181. WHEN `PulseEvidenceBuilder` and `PulseEvidenceSourceRepository` construct/query a sealed evidence packet THEN system SHALL consume the formal `PulseCandidateContext` fields directly, SHALL fail on malformed/dict-like context shapes before packet construction or SQL lookup, and SHALL not retain `getattr(context, ..., default)`, `context.get(...)`, or context helper compatibility paths.
- AC182. WHEN `terminalize_source_row(..., commit=True)` writes `worker_queue_terminal_events` source-row terminal ledger evidence THEN system SHALL require callable connection `transaction` before terminal generation reads or ledger SQL, SHALL reuse the `commit=False` write path inside that transaction, and SHALL not retain naked `conn.commit()` platform terminalization compatibility.
- AC183. WHEN OpenNews REST ingestion scans `/open/news_search` pages THEN system SHALL take REST page limit, max page count, and overlap window from formal source policy or the formal worker fetch limit/cursor, SHALL fail missing `rest_limit`, `max_rest_pages`, or `rest_overlap_ms` contracts instead of silently using integration-local defaults, SHALL keep only provider protocol caps in the integration client, and SHALL not retain source-policy `overlap_ms` alias compatibility outside durable cursor state.
- AC184. WHEN `MacrodataBundleRunner` or `MacroSyncService` reports FRED key state or injects macrodata child-process secrets THEN system SHALL honor the formal root setting `macrodata_fred_api_key_env` exactly, SHALL treat `null` or blank as env lookup disabled, and SHALL not retain runner/service-local `FINANCE_FRED_API_KEY` defaults or `DEFAULT_FRED_API_KEY_ENV` compatibility constants that override settings ownership.
- AC185. WHEN News item processing or NewsRepository writes current `market_scope_json`, `story_identity_json`, or `agent_admission_*` state THEN system SHALL accept only the formal `NewsMarketScope`, `NewsStoryIdentity`, and `NewsItemAgentAdmission` domain result objects, SHALL validate their required fields before SQL, SHALL keep public/projection row normalization separate from write-side command payloads, and SHALL not retain dict/alias/default payload fallback protocols such as `Mapping` current-state inputs, `to_payload` probes, `agent_representative_news_item_id` aliases, or write-side `needs_review` / version defaults.
- AC186. WHEN `PulseCandidateWorker` claims dirty triggers, reschedules capacity-suppressed triggers, marks trigger errors, claims target/candidate edge budgets, evaluates failure-circuit suppression, or computes trigger signatures THEN system SHALL read trigger lease/retry intervals, target/candidate edge budgets, failure-circuit threshold/reasons, and trigger thresholds from formal `settings.workers.pulse_candidate` fields, SHALL define those policy fields in the formal worker settings schema/default workers YAML, SHALL pass them explicitly into repository/policy/helper boundaries, and SHALL not retain worker-local `PULSE_*` budget/lease/retry/failure constants, `PulseTriggerThresholds()` helper defaults, or hard-coded `recent_failure_count >= 3` admission-policy magic.
- AC187. WHEN Pulse admission policy evaluates an existing failed `pulse_agent_jobs` row for retry suppression THEN system SHALL require formal `attempt_count` and `max_attempts` fields to be present and valid, SHALL fail malformed failed-job state before suppressing a new admission, and SHALL not restore missing or invalid `max_attempts` through policy-local defaults such as `or 3`.
- AC188. WHEN notification delivery failure handling classifies a `notification_deliveries` row as retryable or dead THEN system SHALL require formal `attempt_count` and `max_attempts` fields to be present and valid, SHALL fail malformed delivery attempt state before repository SQL or worker outcome classification, and SHALL not restore missing/invalid attempt state through repository or worker-local defaults such as `or 0`, `or 1`, or `or 5`.
- AC189. WHEN `terminalize_source_row(...)` writes `worker_queue_terminal_events` source-row terminal evidence THEN system SHALL require a formal non-negative `attempt_count` from the explicit argument or source row before terminal-generation SQL, SHALL require positive `terminal_generation` values from existing/generation query rows, and SHALL not restore missing attempt or generation state through platform defaults such as `or 0`, `or 1`, or `max(1, int(...))`.
- AC190. WHEN repository terminal-ledger callers pass deleted/returned queue rows into `terminalize_source_row(...)` THEN callers SHALL preserve the source row attempt contract for platform validation, SHALL only pass an explicit `attempt_count` when it is a real caller-owned override, and SHALL not convert missing source-row attempts into explicit zero-attempt overrides before the Queue Terminal platform contract runs.
- AC191. WHEN Token Radar projection converts target/source dirty claims into completion keys for `mark_done(...)` or `mark_error(...)` THEN projection SHALL require a positive `attempt_count` from the claimed row before rank-source population, source projection, or dirty completion, SHALL fail malformed claims as `token_radar_dirty_claim_attempt_contract_required`, and SHALL not restore missing claim attempts through `claim.get("attempt_count") or 0`.
- AC192. WHEN `NewsProjectionDirtyTargetRepository` converts claimed page/source-quality dirty target keys for done, error, delete, or terminalization THEN repository SHALL require a non-negative claimed-row `attempt_count` in the completion key before transaction entry or SQL, SHALL fail malformed completion tokens as `news projection dirty target completion requires attempt_count from claim_due`, and SHALL not restore missing attempts through `key.get("attempt_count") or 0`.
- AC193. WHEN Token Radar target/source dirty repositories convert claimed dirty keys for done or error completion THEN repositories SHALL require positive claimed-row `attempt_count` through direct `key["attempt_count"]` access, SHALL fail malformed completion tokens before SQL, and SHALL not restore missing attempts through `key.get("attempt_count") or 0`.
- AC194. WHEN `MarketTickCurrentDirtyTargetRepository` converts claimed dirty target keys for done or error completion THEN repository SHALL require positive claimed-row `attempt_count` through direct `claim["attempt_count"]` access, SHALL fail malformed completion tokens before SQL, and SHALL not restore missing attempts through `claim.get("attempt_count") or 0`.
- AC195. WHEN Token Profile Current, Token Image Source, or Asset Profile Refresh dirty repositories convert claimed dirty keys for done, error, reschedule, or terminal completion THEN repositories SHALL require positive claimed-row `attempt_count` through direct `claim["attempt_count"]` access, SHALL fail malformed completion tokens before SQL, and SHALL not restore missing attempts through `claim.get("attempt_count") or 0`.
- AC196. WHEN Discovery lookup, Narrative Admission, or Pulse Trigger dirty repositories convert claimed dirty keys for done, error, reschedule, or terminal completion THEN repositories SHALL require positive claimed-row `attempt_count` through direct `claim["attempt_count"]` access, SHALL fail malformed completion tokens before SQL, and SHALL not restore missing attempts through `claim.get("attempt_count") or 0` or silently filtered no-op records.
- AC197. WHEN Event Anchor Backfill or Resolution Refresh workers choose temporary retry, done, terminal, or retry-budget branches from claimed control rows THEN workers SHALL require positive claimed-row `attempt_count` through direct `row["attempt_count"]` or `claim["attempt_count"]` access, SHALL fail malformed claim state before branching, and SHALL not restore missing attempts through `row.get("attempt_count") or 0` or `claim.get("attempt_count") or 0`.
- AC198. WHEN Pulse agent job execution/audit/release/failure paths or Macro Sync retry-budget classification branch on claimed control rows THEN they SHALL require positive claimed-row `attempt_count` through direct `job["attempt_count"]` or `window["attempt_count"]` access, SHALL require positive claimed-row `max_attempts` where retry/dead budget classification depends on it, SHALL fail malformed claim state before repository SQL or audit construction, and SHALL not restore missing attempts through `job.get("attempt_count") or 0`, `job.get("max_attempts") or 3`, `window.get("attempt_count") or 0`, or `window.get("max_attempts") or 1`.
- AC199. WHEN `NewsItemProcessWorker` branches on claimed item rows for deterministic item processing, retryable failure, terminal failure, page dirty enqueue, or item-brief dirty enqueue THEN worker SHALL require positive claimed-row `processing_attempts` and non-empty claimed-row `processing_lease_owner` through direct `item["processing_attempts"]` and `item["processing_lease_owner"]` access, SHALL fail malformed claim rows before deterministic writes or failure state writes, and SHALL not restore missing claim fields through `item.get("processing_attempts", 0)`, `item.get("processing_attempts") or 0`, or `item.get("processing_lease_owner") or ""`.
- AC200. WHEN dirty target, source dirty, discovery lookup, event-anchor, Narrative Admission, Pulse Trigger, News projection, Asset Market profile/image/refresh, or Token Radar projection completion keys are built from claimed rows THEN system SHALL require positive claimed-row `attempt_count` and non-empty claimed-row `lease_owner`, SHALL fail missing owner fields before rank-source work, source projection, done/error/reschedule/terminal SQL, or terminal ledger writes, and SHALL not restore missing owners through `claim.get("lease_owner") or ""`, `key.get("lease_owner") or ""`, or `row.get("lease_owner") or ""`.
- AC201. WHEN dirty target, source dirty, discovery lookup, Narrative Admission, Pulse Trigger, News projection, Asset Market profile/image/refresh/current, or Token Radar projection completion keys are built from claimed rows THEN system SHALL require claimed-row `payload_hash` before rank-source work, source projection, done/error/reschedule SQL, or queue completion, SHALL fail malformed payload keys before state mutation, and SHALL not restore missing payload hashes through `claim.get("payload_hash") or ""` or `key.get("payload_hash") or ""`.
- AC202. WHEN Token Image Source dirty completion keys are built for done or error THEN repository SHALL require claimed-row `source_url_hash` through direct `claim["source_url_hash"]` access, SHALL fail malformed target keys before SQL, and SHALL not restore missing source hashes by hashing `claim.get("source_url") or ""` or using `claim.get("source_url_hash") or _source_url_hash(...)`.
- AC203. WHEN `PulseCandidateWorker` suppresses a token-radar exit trigger and writes `pulse_candidate_edge_state.trigger_signature` THEN worker SHALL require the claimed dirty-trigger `payload_hash` through direct `claim["payload_hash"]` access, SHALL fail malformed exit claims before admission writes, and SHALL not restore missing payload hashes through `str(claim.get("payload_hash") or "")`.
- AC204. WHEN Token Radar projection decides whether previous/current rank rows changed for Pulse, Narrative Admission, or Token Profile Current fan-out, or hydrates a current row from target features, THEN projection SHALL require row `payload_hash` through direct `row["payload_hash"]` access, SHALL fail malformed rows before skip decisions or hydration, and SHALL not restore missing payload hashes through `previous.get("payload_hash") or ""` or `row.get("payload_hash") or ""`.
- AC205. WHEN `DiscoveryRepository` terminalizes exhausted lookup claims by deleting `token_discovery_dirty_lookup_keys` rows and writing `worker_queue_terminal_events` evidence THEN repository SHALL require deleted source-row `payload_hash` through direct `row["payload_hash"]` access, SHALL fail missing or blank source hashes before terminal ledger SQL, and SHALL not restore missing source hashes through `row.get("payload_hash") or ""`.
- AC206. WHEN Macro observation-series refresh compares selected rows with existing `macro_observation_series_rows` current rows THEN repository SHALL require existing current-row `payload_hash` through direct `row["payload_hash"]` access, SHALL fail missing or blank existing signatures before changed/unchanged decisions or delete/insert SQL, and SHALL not restore missing hashes through `str(row.get("payload_hash") or "")` or `row.get("payload_hash") or ""`.
- AC207. WHEN `/api/stocks-radar` builds per-symbol `source_event_ids` THEN the SQL SHALL rank mentions per target inside PostgreSQL, SHALL bound the public event-id provenance array with `STOCKS_RADAR_SOURCE_EVENT_LIMIT`, SHALL keep full-window mention/author/latest aggregations intact, and SHALL not restore the previous unbounded `ARRAY_AGG(event_id ORDER BY received_at_ms DESC, event_id DESC) AS source_event_ids` read payload.
- AC208. WHEN News agent-admission duplicate lookup matches provider-native article ids THEN repository SQL SHALL use normalized `news_item_observation_edges.provider_article_key` joins, SHALL keep `provider_article_keys_json` as compact evidence payload only, and SHALL not expand `provider_article_keys_json` with `jsonb_array_elements_text(...)` in `_agent_exact_duplicate_context(...)` or `load_agent_admission_contexts(...)`.
- AC209. WHEN Signal Pulse public read paths receive `q` search THEN repository SHALL strip whitespace and treat blank `q` as no search filter, SHALL keep non-empty substring search backed by PostgreSQL trigram GIN indexes on `pulse_candidates.symbol`, `pulse_candidates.subject_key`, `pulse_candidates.target_id`, `pulse_agent_jobs.subject_key`, and `pulse_agent_jobs.target_id`, and SHALL not produce `ILIKE '%%'` scans or unindexed public `%...%` search contracts.
- AC210. WHEN ops diagnostics reports Asset Market provider health THEN diagnostics SHALL consume the formal `ProviderHealth` contract or an explicit mapping with `provider`, `capabilities`, and `configured`, SHALL fail malformed health items as a runtime contract error, and SHALL not retain generic `_object_payload(...)`, `vars(...)`, `__dict__`, or dataclass-reflection compatibility paths that turn bad provider wiring into `provider=unknown` / disabled-looking rows.
- AC211. WHEN Pulse evidence completeness gate evaluates sealed evidence THEN it SHALL require the formal `PulseEvidencePacket` contract, SHALL fail malformed packet inputs with `pulse_evidence_packet_contract_required`, SHALL read packet fields directly and convert only formal packet submodels, and SHALL not retain `PulseEvidencePacket | Any`, `getattr(packet, ...)`, arbitrary `model_dump` probes, `__dict__`, `vars(...)`, `_model_items(...)`, or `_model_mapping(...)` reflection compatibility.
- AC212. WHEN Pulse claim evidence verifier validates final decision refs THEN it SHALL require the formal sealed `PulseEvidencePacket` and strict `FinalDecision` contracts, SHALL fail malformed verifier inputs with `pulse_claim_verifier_packet_contract_required` or `pulse_claim_verifier_final_decision_contract_required`, SHALL read allowed refs and final refs from model fields directly, and SHALL not retain `PulseEvidencePacket | Any`, `FinalDecision | Any`, `getattr(packet, ...)`, `getattr(final_decision, ...)`, dict-ref fallback, or `_sequence(...)` compatibility.
- AC213. WHEN Pulse decision runtime builds the `pulse_decision` stage spec THEN it SHALL require formal `PulseEvidencePacket` and `EvidenceCompletenessGateResult` models, SHALL fail malformed stage inputs with `pulse_decision_stage_packet_contract_required` or `pulse_decision_stage_gate_contract_required`, SHALL require the model-execution adapter to re-validate JSON context into those formal models before domain stage construction, and SHALL not retain `_model_payload(evidence_packet)`, `_model_payload(evidence_gate)`, arbitrary `model_dump` probes, dict packet/gate stage-spec compatibility, or `PulseEvidencePacket | dict` failure-helper packet compatibility.
- AC214. WHEN News item processing writes deterministic current facts for extracted entities, token mentions, or fact candidates THEN `NewsRepository` SHALL accept only formal `NewsEntity`, `NewsTokenMention`, and `NewsFactCandidate` domain objects, SHALL fail malformed payload objects before INSERT, SHALL keep worker-side payload normalization limited to mappings and formal dataclasses, and SHALL not retain `_object_payload(...)`, arbitrary `model_dump`, `vars(...)`, `__dict__`, or `__slots__` reflection compatibility in the production fact-write boundary.
- AC215. WHEN Pulse recommendation clipping, cost guarding, or write gating reads gate decisions after final decision generation THEN those stages SHALL require formal `PulseGateResult`, `EvidenceCompletenessGateResult`, `ClaimEvidenceVerificationResult`, and `PulseSourceQualityDecision` contracts as applicable, SHALL fail malformed gate inputs with explicit `pulse_*_contract_required` errors, SHALL read fields directly, and SHALL not retain `Any` gate signatures, optional evidence/claim/source-quality defaults, or `getattr(...)` compatibility that restores malformed inputs to complete/public/valid defaults.
- AC216. WHEN `PulseCandidateJobService` classifies a completed agent run outcome after claim verification THEN run-outcome logic SHALL require the formal `ClaimEvidenceVerificationResult`, SHALL fail malformed verifier inputs with `pulse_run_outcome_claim_verification_contract_required`, SHALL derive unknown-ref outcomes from `claim_verification.unknown_ref_ids` directly, and SHALL not retain a separate `claim_verification_valid` boolean or optional verifier object fallback.
- AC217. WHEN Pulse stage-output normalization repairs final decision event-id fields THEN it SHALL require the formal sealed `PulseEvidencePacket`, SHALL fail malformed packet inputs with `pulse_stage_output_normalization_packet_contract_required`, SHALL read `source_event_ids` and `allowed_evidence_refs` from model fields directly, and SHALL not retain `evidence_packet: Any`, dict packet lookup, dict/object evidence-ref reflection, `_allowed_refs(...)`, or `_ref_value(...)` compatibility.
- AC218. WHEN Pulse deterministic eval grades stored eval-case JSON THEN it SHALL re-validate `input_json.context.evidence_packet` into the formal `PulseEvidencePacket` before allowed-ref checks, SHALL fail partial or malformed packet JSON as missing evidence, SHALL read refs from `packet.allowed_evidence_refs` model fields directly, and SHALL not retain partial dict packet grading via `_mapping(context.get("evidence_packet"))`, `_list(packet.get("allowed_evidence_refs"))`, or dict-ref lookup.
- AC219. WHEN Pulse request-audit metadata builds input hashes, trace metadata, or evidence packet schema/hash fields THEN it SHALL re-validate `context["evidence_packet"]` into the formal `PulseEvidencePacket`, SHALL fail malformed audit context as `pulse_decision_request_audit_packet_contract_required`, SHALL derive packet payloads through `_agent_packet_payload(...)`, and SHALL not retain top-level `evidence_packet_hash` fallback, `return dict(context)`, or `packet_payload or context` compatibility.
- AC220. WHEN Pulse model-execution adapter converts gateway results or agent execution errors into `StageRunAudit` rows THEN it SHALL require formal `AgentExecutionResult` and `AgentExecutionRequestAudit` / `AgentExecutionResultAudit` contracts, SHALL fail malformed execution results or audit objects as `pulse_decision_execution_result_contract_required` or `pulse_decision_execution_audit_contract_required`, SHALL read audit fields directly, and SHALL not retain `getattr(audit, ...)`, `getattr(exc, ...)`, or missing-audit field synthesis compatibility.
- AC221. WHEN Pulse request-audit metadata builds input hashes or trace `evidence_gate` fields THEN it SHALL require formal `EvidenceCompletenessGateResult`, SHALL fail malformed gate inputs as `pulse_decision_request_audit_gate_contract_required`, SHALL derive gate payloads through `completeness.to_json()`, and SHALL not retain raw `completeness: dict[str, Any]`, `"evidence_gate": completeness`, or dict gate replay-hash compatibility.
- AC222. WHEN Pulse request-audit metadata records runtime manifest state THEN it SHALL require a non-empty `runtime_manifest["runtime_version"]`, SHALL fail missing or blank runtime versions as `pulse_decision_runtime_manifest_version_required`, SHALL write that validated value into trace and run audit metadata, and SHALL not retain `runtime_manifest.get("runtime_version") or ""` empty-default compatibility.
- AC223. WHEN Pulse request-audit metadata records execution identity THEN it SHALL require non-empty `run_id`, claimed-row `job_id`, model, artifact version hash, workflow name, and agent name, SHALL fail malformed identity as explicit `pulse_decision_request_audit_*_required` errors, SHALL write only validated identity values into trace/run audit metadata, and SHALL not retain `str(... or "")` or `job.get("job_id") or ""` empty-placeholder compatibility.
- AC224. WHEN Pulse request-audit metadata records runtime model identity THEN it SHALL require `runtime_manifest["model"]["model"]` and `runtime_manifest["model"]["artifact_version_hash"]` to match the request-audit model and artifact hash, SHALL fail mismatches as `pulse_decision_runtime_manifest_model_mismatch` or `pulse_decision_runtime_manifest_artifact_version_hash_mismatch`, and SHALL not allow runtime hash lineage and run audit lineage to describe different executable artifacts.
- AC225. WHEN `PulseCandidateJobService` persists `pulse_agent_runs` or run-step prompt/schema metadata from request-audit output THEN it SHALL validate the request-audit payload as the ledger contract, SHALL require non-empty backend, execution trace id, workflow, agent, artifact hash, prompt/schema, runtime version/hash, input hash, and trace metadata, SHALL require runtime version/hash/artifact identity to match the current runtime manifest, SHALL require provider result audits to carry `output_hash` before done finalization, SHALL derive run usage from stage audit rows, and SHALL not restore missing audit fields through local constants, `_artifact_hash(...)`, `_stable_hash(...)`, empty trace/usage dicts, or result-audit output-hash fallback.
- AC226. WHEN `PulseCandidateJobService` decides whether an agent failure should release a job to provider cooldown as no-start backpressure THEN it SHALL require a formal `AgentExecutionError` with `error_class` in the no-start backpressure set and `execution_started is False`, SHALL treat loose exception audit dicts or alias fields as ordinary failures, and SHALL not infer cooldown release from `exc.audit`, `exc.agent_audit`, `agent_error_class`, `agent_execution_started`, or `_agent_error_class(...)` reflection compatibility.
- AC227. WHEN `PulseCandidateJobService` handles worker hard-timeout cancellation and decides whether cleanup is before or after agent execution THEN it SHALL read `execution_started` only from formal `AgentExecutionCancelled`, SHALL otherwise use the service-local `run_started` state, SHALL treat loose cancellation audit dicts or alias fields as non-authoritative, and SHALL not infer timeout retry/dead classification from `exc.audit`, `exc.agent_audit`, or reflective `execution_started` attributes.
- AC228. WHEN `PulseCandidateJobService` builds a Pulse agent `run_id` or writes final job/run lineage from a claimed `pulse_agent_jobs` row THEN it SHALL require non-empty claimed-row `job_id`, `trigger_signature`, and `timeline_signature` plus positive `attempt_count` before opening repository sessions or deriving runtime/audit state, SHALL use that validated job-run identity for `run_id`, `pulse_agent_runs.job_id`, and job success completion, and SHALL not restore missing identity segments through `job.get("job_id") or ""`, `job.get("trigger_signature") or ""`, or `job.get("timeline_signature") or ""`.
- AC229. WHEN `LiteLLMPulseDecisionClient` builds an `AgentStageSpec` for the Pulse `pulse_decision` stage THEN it SHALL validate the request-audit trace metadata contains the same non-empty `run_id` as the current pipeline call, SHALL require a non-empty stage group id from the formal stage input evidence packet, SHALL fail malformed runtime/audit output before gateway request audit or model execution, and SHALL not restore missing trace/group identity through `audit.get("trace_metadata") or {}`, `_group_id(...) or run_id`, or `str(run_id or "")` fallbacks.
- AC230. WHEN `LiteLLMPulseDecisionClient` is constructed with a workflow name THEN it SHALL require the provided workflow identity to be non-empty, SHALL allow the default `WORKFLOW_NAME` only when the constructor argument is omitted, and SHALL not restore explicit blank or `None` workflow values through `str(workflow_name or "").strip() or WORKFLOW_NAME`.
- AC231. WHEN Token Radar projection builds target-feature or current serving rows THEN it SHALL require formal `target_type_key` and `identity_id` serving identity fields before payload hash, generation hash, first-seen lookup, or row upsert, SHALL derive unresolved attention identities from stable lookup keys such as `LookupKey/symbol:...`, and SHALL not restore missing serving identity through `target_type`, `target_id`, or `intent_id` fallback.
- AC232. WHEN Token Radar projection or dirty repositories build target/source dirty completion keys after a claimed row THEN target dirty keys SHALL require formal `target_type_key` and `identity_id`, source dirty keys SHALL require formal `projection_version`, `source_event_id`, `target_type_key`, and `identity_id`, malformed claims SHALL fail before rank-source work, source projection, done/error SQL, or CAS key construction, and completion code SHALL not restore missing identity through `claim.get(...)` or `key.get(...)` aliases such as `target_type`, `target_id`, `intent_id`, or `event_id`.
- AC233. WHEN News repositories or queries persist/read deterministic entity, token mention, or fact candidate state THEN they SHALL depend only on lower-layer domain types such as `NewsEntity`, `NewsTokenMention`, and `NewsFactCandidate`, SHALL keep deterministic extraction/building logic in services called by workers, and SHALL not import `news_intel.services`, runtime modules, or read models from repository/query code.
- AC234. WHEN repositories or queries need deterministic canonical identity, fingerprint, or current payload-hash primitives THEN those primitives SHALL live in lower-layer domain `types` modules, repository/query code SHALL import them only from `types`/interfaces/platform primitives, and architecture tests SHALL reject any repository/query import from same-domain `services`, `runtime`, or `read_models` without allowlist exceptions.
- AC235. WHEN Token Radar dirty target/source projection claims due work or schedules dirty error retries THEN lease and retry intervals SHALL come from formal `settings.workers.token_radar_projection.lease_ms` and `.retry_ms`, `TokenRadarProjectionWorker` SHALL pass those values explicitly into `TokenRadarProjection.rebuild_dirty_targets(...)`, and projection service code SHALL not retain service-local dirty queue lease/retry constants or hidden policy defaults.
- AC236. WHEN Token Radar private cache retention removes old `token_radar_target_features` or `token_radar_rank_source_events` rows THEN the owner SHALL be the single `TokenRadarProjectionWorker`, retention SHALL use formal `settings.workers.token_radar_projection.private_cache_retention_enabled` and `.private_cache_retention_ms`, pruning SHALL execute through explicit `TokenRadarProjection.prune_private_cache(...)` outside `refresh_rank_set`, and repository SQL SHALL be bounded by a worker batch `LIMIT` instead of unbounded publish-path deletes.
- AC237. WHEN `docs/TECH_DEBT.md` records open storage debt THEN rows SHALL describe unresolved current-state work only; legacy asset-stack and duplicate-token FK-index debt that is already resolved by `20260516_0050_drop_legacy_asset_stack.py` and `20260517_0053_reconcile_legacy_asset_stack_drop.py` SHALL live in `Closed`, and architecture tests SHALL fail if those resolved claims return to `Open`.
- AC238. WHEN `ResolutionRefreshWorker` claims discovery lookup work, marks lookup rows running, or reschedules hot not-found lookup claims THEN lookup lease/running timeout and hot not-found retry cadence SHALL come from formal `settings.workers.resolution_refresh.lease_ms` and `.hot_not_found_retry_ms`, SHALL be passed explicitly into `DiscoveryRepository` boundaries, SHALL be present in the formal settings schema/default workers YAML, and runtime/repository code SHALL not retain `RUNNING_LOOKUP_TIMEOUT_MS` or `HOT_NOT_FOUND_RETRY_MS` local policy constants.
- AC239. WHEN discovery lookup due work is consumed in production THEN it SHALL go through the leasing `DiscoveryRepository.claim_due_lookup_keys(...)` state transition, SHALL not expose a production `DiscoveryRepository.due_lookup_keys(...)` read-only peek helper or unused `since_ms` compatibility argument, and tests that need due-order inspection SHALL keep that SQL local to test code rather than preserving a second production queue-consumer API.
- AC240. WHEN `TokenImageMirrorWorker` schedules image asset errors or dirty-source errors THEN retry cadence SHALL come from formal `settings.workers.token_image_mirror.retry_ms`, SHALL be passed explicitly into `TokenImageMirrorService`, and service code SHALL not retain `TOKEN_IMAGE_MIRROR_RETRY_MS`, constructor retry defaults, or any service-local retry policy fallback.
- AC241. WHEN `NarrativeAdmissionWorker` computes deterministic source-set admissions THEN hot-rank and minimum-score thresholds SHALL come from formal `settings.workers.narrative_admission`, SHALL be passed explicitly into `NarrativeAdmissionService`, and service code SHALL not retain constructor threshold defaults or unused carry-forward TTL compatibility such as `carry_ttl_ms`.
- AC242. WHEN `PulseCandidateJobService` constructs a sealed `PulseEvidencePacket` with market facts THEN market-fact freshness SHALL come from formal `settings.workers.pulse_candidate.evidence_market_freshness_ms`, SHALL be passed explicitly into `PulseEvidenceBuilder` and `PulseEvidenceSourceRepository.list_market_facts(...)` with the job run's `now_ms`, SHALL be present in the formal settings schema/default workers YAML, and service/repository code SHALL not retain builder-local freshness defaults, repository-local `max_age_ms` / `now_ms` defaults, or default-current-clock fallbacks.
- AC243. WHEN `CexOiRadarBoardWorker` enriches board/detail rows with CoinGlass liquidation level bands THEN the level-band limit SHALL come from formal `settings.workers.cex_oi_radar_board.coinglass_level_limit`, SHALL be passed explicitly into `enrich_rows_with_coinglass(...)` and `enrich_row_with_coinglass(...)`, and enrichment service code SHALL not retain `level_limit` constructor/function defaults or service-local level-band policy.
- AC244. WHEN `CexOiRadarBoardWorker` builds Binance OI radar rows THEN period and build limit SHALL come from formal `settings.workers.cex_oi_radar_board` fields and the worker's bounded `min(universe_limit, batch_size)` budget, SHALL be passed explicitly into `build_binance_oi_radar_rows(...)`, and builder service code SHALL not retain `period` or `limit` defaults such as `"5m"` or `500`.
- AC245. WHEN `AssetProfileRefreshWorker` writes ready/missing/error provider profile source-cache rows and reschedules their refresh targets THEN ready/missing/error refresh intervals SHALL come from formal `settings.workers.asset_profile_refresh.ready_refresh_ms`, `.missing_refresh_ms`, and `.error_refresh_ms`, SHALL be present in the formal settings schema/default workers YAML, SHALL be computed once by the worker and passed explicitly as `next_refresh_at_ms` to service/repository writes and as matching `due_at_ms` to refresh-target reschedules, and worker/service/repository code SHALL not retain `READY_REFRESH_MS`, `MISSING_REFRESH_MS`, `ERROR_REFRESH_MS`, or service-local `now_ms + constant` refresh policy.
- AC246. WHEN `PulseCandidateWorker` classifies dirty-trigger admission through `PulseAdmissionPolicy` THEN recent-failure count, failure-circuit threshold, and timeline-debounce duration SHALL be explicit caller inputs from formal `settings.workers.pulse_candidate` and repository reads, `timeline_debounce_seconds` SHALL be present in the formal settings schema/default workers YAML, and `PulseAdmissionPolicy.classify(...)` SHALL not retain defaults for `recent_failure_count`, `failure_circuit_per_hour`, or `timeline_debounce_seconds`.
- AC247. WHEN `NotificationWorker` evaluates notification rules to create `notifications` and `notification_deliveries` candidates THEN the evaluation timestamp SHALL be the explicit worker-run `now_ms`, `NotificationRuleEngine.evaluate(...)` SHALL require `now_ms: int`, and notification rule service code SHALL not retain a service-local current-clock fallback such as optional `now_ms`, `_now_ms()`, or `import time`.
- AC248. WHEN notification rule evaluation scans watched-account activity or News high-signal candidates THEN watched activity recency, News high-signal recency, News high-signal query minimum, and News high-signal query multiplier SHALL come from formal `settings.notifications` fields, SHALL be present in the formal settings schema/default config YAML, and notification rule service code SHALL not retain service-local query policy constants such as `WATCHED_ACTIVITY_WINDOW_MS`, `NEWS_HIGH_SIGNAL_QUERY_MIN_LIMIT`, `NEWS_HIGH_SIGNAL_QUERY_MULTIPLIER`, or `NEWS_HIGH_SIGNAL_RECENCY_WINDOW_MS`.
- AC249. WHEN notification rule evaluation paginates Signal Pulse candidates THEN page budget SHALL come from formal `settings.notifications.signal_pulse_max_pages`, SHALL be present in the formal settings schema/default config YAML, and notification rule service code SHALL not retain `MAX_SIGNAL_PULSE_NOTIFICATION_PAGES` or any service-local Signal Pulse notification page cap.
- AC250. WHEN `NotificationWorker` creates external `notification_deliveries` rows THEN delivery retry budget SHALL be passed explicitly from formal `settings.workers.notification_delivery.max_attempts` through the runtime factory, `NotificationWorker.__init__(...)` SHALL require `delivery_max_attempts: int`, and rule-worker code SHALL not retain a constructor default such as `delivery_max_attempts: int = 5`.
- AC251. WHEN `NewsItemBriefWorker` reuses completed or failed `news_item_agent_runs` rows to restore current brief state, write failed-current state, or audit invalid completed runs THEN the persisted run row SHALL provide a non-empty `run_id`, malformed run identity SHALL fail the dirty target before model execution or current-brief upsert, and runtime code SHALL not retain `str(run.get("run_id") or "")`, `source_run_id = str(...)`, or missing-run-id `return None` fallbacks.
- AC252. WHEN Pulse agent jobs are enqueued into `pulse_agent_jobs` THEN the retry budget SHALL be passed explicitly from formal `settings.workers.pulse_candidate.max_attempts` through the worker/caller into `PulseJobsRepository.enqueue_job(...)`, and repository code SHALL not retain `max_attempts: int = 3`, any `max_attempts: int =` enqueue default, or test/runtime helper defaults that synthesize a retry budget.
- AC253. WHEN account-alert read rows are queried through `AccountAlertService` THEN the caller SHALL pass the alert `window` and `limit` explicitly, API/CLI/notification callers SHALL remain the owners of those query boundaries, and read-service code SHALL not retain `window: str = "24h"`, `window: str =`, `limit: int = 50`, or `limit: int =` defaults.
- AC254. WHEN token-intel search rows are queried through `SearchService` THEN the caller SHALL pass `limit`, `scope`, and `window` explicitly, API/CLI callers SHALL own public defaults and validation, CLI `parallax search` SHALL pass its parsed `window`, and read-service code SHALL not retain `limit: int =`, `scope: str =`, `window: str =`, or `WINDOW_MS.get(window...)` fallback semantics.
- AC255. WHEN token-target timeline or post rows are queried through `TokenTargetSocialTimelineService` or `TokenTargetPostsService` THEN the caller SHALL pass valid `window`, `scope`, and `limit` explicitly, API/Token Case callers SHALL own public defaults and validation, and read-service code SHALL not retain `WINDOW_MS.get(window...)`, default-bucket unknown-window behavior, or direct `watched_only=scope == "matched"` fallback semantics that convert malformed scope into `all`.
- AC256. WHEN Token Radar projection computes source scoring windows, rank-source repair analysis bounds, or projected group baselines THEN projection code SHALL resolve windows through required formal `WINDOW_MS[window]` entries, SHALL fail empty or malformed work-item windows before using repair/read widths, and SHALL not retain `WINDOW_MS.get(window...)`, `default=WINDOW_MS["24h"]`, `WINDOW_MS["1h"]` fallback semantics, or implicit 1h/24h projection window recovery.
- AC257. WHEN Pulse timeline context is built for a candidate trigger THEN the caller SHALL pass valid `window` and `scope` explicitly, context code SHALL resolve windows through `WINDOW_MS[window]`, SHALL reject malformed scopes before computing selected posts or timeline signatures, and SHALL not retain `window="1h"`, `scope="all"`, `WINDOW_MS.get(window...)`, or `windows.get(window...)` fallback semantics.
- AC258. WHEN authenticated API routes validate radar/search/pulse/recent-event `scope` query params THEN route defaults SHALL own public default values, `_scope(...)` SHALL accept only supported scopes and raise `invalid_scope` for malformed values, and API validator code SHALL not retain unknown-scope fallback semantics such as `return value if value in SCOPES else "matched"` or `else "matched"`.
- AC259. WHEN CLI ops token-capture-tier rank-set repair computes its repair `since_ms` THEN it SHALL resolve the operator/helper window through required `WINDOW_MS[window]`, SHALL fail malformed direct-call windows before dry-run reads or execute queue writes, and SHALL not retain `WINDOW_MS.get(parsed_window...)` or `WINDOW_MS["24h"]` fallback semantics in the repair helper.
- AC260. WHEN ops diagnostics payloads are built below the API route THEN callers SHALL pass `since_hours`, `window`, and `scope` explicitly, the API route SHALL remain the owner of public defaults and validation, and runtime diagnostics code SHALL not retain `since_hours: int =`, `window: str =`, or `scope: str =` fallback semantics.
- AC261. WHEN Signal Pulse freshness health SQL is reached through repository/service health contracts THEN callers SHALL pass `since_hours` explicitly, public read-model/CLI callers SHALL remain the owners of 4h or operator-specified health horizons, and Pulse freshness health code SHALL not retain `since_hours: int = 4` or `since_hours: int =` fallback semantics.
- AC262. WHEN Pulse recommendation clipping changes a decision to `ignore` or `abstain` THEN it SHALL preserve an existing validated `playbook.monitoring_horizon`, SHALL fail malformed decision payloads missing that horizon, and recommendation clipper code SHALL not retain `or "1h"` or local monitoring-horizon fallback semantics.
- AC263. WHEN Macro asset correlation payloads are built below `/api/macro/assets/correlation` THEN callers SHALL pass `window` explicitly, the API route SHALL remain the owner of the public `60d` default and invalid-window validation, and the correlation builder SHALL not retain `window: str = "60d"` or service-local correlation-window fallback semantics.
- AC264. WHEN Pulse candidate or Narrative admission workers process claimed dirty targets THEN claimed `window` and `scope` SHALL be validated against formal worker settings before token-radar, timeline, admission-target, or source-set reads, malformed dimensions SHALL fail the dirty claim through error/retry, and worker code SHALL not retain `scope == "matched"` as an implicit unknown-scope-to-all fallback or unknown narrative window fallback such as `.get(window, 86_400_000)`.
- AC265. WHEN Token Radar projection dirty targets are claimed or rank sets are published THEN the caller SHALL pass `limit`, `rank_limit`, and `lease_owner` explicitly from the formal projection worker policy, `TokenRadarProjectionWorker` SHALL remain the single runtime owner of dirty claim and rank publish work width, and `TokenRadarProjection` SHALL not retain `limit=100`, `rank_limit=100`, or `lease_owner="token_radar_projection"` service defaults.
- AC266. WHEN Watchlist handle overview reads source events for cluster construction THEN the API/read-service boundary SHALL pass explicit overview source and cluster limits, repository SQL SHALL compute aggregate metrics separately from a bounded source-event sample with `LIMIT %s`, and Watchlist repository/service code SHALL not retain `limit=500`, optional read config defaults, or unbounded per-handle source-event scans before token-resolution fan-out.
- AC267. WHEN PulseCandidateWorker terminalizes exhausted stale-running `pulse_agent_jobs` THEN the batch width SHALL come from formal `settings.workers.pulse_candidate.stale_running_terminalization_batch_size`, the worker/helper SHALL pass that `limit` explicitly into `PulseJobsRepository.terminalize_exhausted_stale_running_jobs(...)`, and the repository/helper SHALL not retain `limit=100` or any repository-local terminalization batch default.
- AC268. WHEN NewsItemBriefWorker reuses completed runs, records provider failures, or refreshes market-wide agent admission THEN it SHALL consume formal `NewsItemBriefValidationResult`, `AgentExecutionRequestAudit | AgentExecutionResultAudit`, and `NewsItemAgentAdmission` contracts directly, SHALL fail malformed audit/admission objects before ledger/current writes, and SHALL not retain `getattr(validation, ...)`, `getattr(..., "model_dump")`, dataclass/asdict, `__slots__`, or `_object_payload` reflection fallbacks.
- AC269. WHEN News item-brief source-backed entity/domain support derives market domains from input packets THEN it SHALL consume formal `NewsItemBriefEntityLane` rows from `NewsItemBriefInputPacket.entity_lanes`, SHALL fail loose mapping/entity-like objects through normal attribute-contract failure, and SHALL not retain `getattr(entity, ...)`, missing-field defaults, or object-reflection fallbacks for entity lane fields.
- AC270. WHEN Signal Pulse public candidates are listed through `PulseReadRepository.list_candidates(...)` THEN the caller SHALL pass the public read `limit` explicitly from API/service validation, repository SQL SHALL bound rows from that explicit value, and the repository SHALL not retain `limit=50` or any repository-owned public list-width default.
- AC271. WHEN Token Radar projection control-plane diagnostics list `projection_runs` or `projection_dirty_ranges` THEN callers SHALL pass explicit `limit` values, repository SQL SHALL use only those explicit limits, and `ProjectionRepository` SHALL not retain `list_runs(limit=20)` or `list_dirty_ranges(limit=50)` defaults.
- AC272. WHEN token resolution refresh reprocesses intents and enqueues `token_radar_source_dirty_events` THEN it SHALL consume formal `TokenIntentResolutionDecision` / `DeterministicResolution` results directly, SHALL fail malformed loose resolver decision objects before source-dirty enqueue, and SHALL not retain `getattr(decision, ...)`, `hasattr(decision, ...)`, `decision.get("target_type"...)`, `decision.get("target_id"...)`, or `decision.get("event_id"...)` object-reflection fallback.
- AC273. WHEN `IngestService` commits token intent resolutions, lookup keys, discovery lookup keys, market capture context, or `token_radar_source_dirty_events` from resolver decisions THEN it SHALL consume formal `TokenIntentResolutionDecision` / `DeterministicResolution` results directly, SHALL fail malformed loose or dict-like resolver decision objects before source-dirty enqueue, and SHALL not retain `_decision_value(...)`, `isinstance(decision, dict)`, `decision.get(...)`, `getattr(decision, ...)`, or `hasattr(decision, ...)` decision-shape compatibility.
- AC274. WHEN `NarrativeReadModel` hydrates Token Radar rows with historical `discussion_digest` context THEN it SHALL require formal row identity fields `target_type` and `target_id` before digest lookup, SHALL report explicit missing narrative context for rows that only carry legacy `type` / `id` aliases, and SHALL not retain `row.get("target_type") or row.get("type")`, `row.get("target_id") or row.get("id")`, `row.get("type")`, or `row.get("id")` target-identity compatibility.
- AC275. WHEN `CexDetailSnapshotRepository` hashes or upserts `cex_detail_snapshots` serving rows THEN it SHALL require formal `snapshot_id`, `target_type`, `target_id`, `exchange`, and `native_market_id` before payload hash or SQL, SHALL fail malformed snapshots before serving-row writes, and SHALL not retain repository-local identity fallbacks such as `snapshot.get("target_type") or "CexToken"` or `snapshot.get("exchange") or "binance"`.
- AC276. WHEN `CexOiRadarBoardWorker` builds `cex_detail_snapshots` from CEX radar rows THEN `build_cex_detail_snapshot(...)` SHALL require non-empty `native_market_id` and stable CEX target identity before current snapshot construction, SHALL fail malformed rows before board/detail publication rather than silently skipping detail rows, and SHALL not retain `cex_token:unknown`, `return target_id or ...`, or `if row.get("native_market_id")` compatibility paths.
- AC277. WHEN `build_binance_oi_radar_rows(...)` consumes the selected Binance universe routes for `cex_oi_radar_rows` THEN it SHALL require non-empty route `native_market_id` before provider IO, SHALL fail malformed universe rows through the worker attempt-failure path instead of publishing a success empty/partial board, and SHALL not retain `if not symbol: continue` or `str(route.get("native_market_id") or "")...` skip/default compatibility.
- AC278. WHEN `CexOiRadarRepository` hashes `cex_oi_radar_rows` current-board payloads THEN it SHALL include provider-observed market freshness only, SHALL ignore `observed_at_source="computed"` fallback timestamps and successful empty-board attempt times for content signatures, SHALL preserve unchanged projections as zero serving-row writes, and SHALL not retain direct `row.get("observed_at_ms")` hash payload semantics.
- AC279. WHEN `CexOiRadarRepository` constructs `cex_oi_radar_rows` board keys, row ids, payload hashes, or upsert parameters THEN it SHALL require non-empty formal `period`, `target_id`, and `native_market_id` before SQL, SHALL fail malformed writer output before serving-row writes, and SHALL not retain empty-string identity compatibility through `str(period)`, `str(row["target_id"])`, direct `row["target_id"]`, or direct `row["native_market_id"]` in current-board identity/payload boundaries.
- AC280. WHEN `CexDerivativeSeriesRepository` upserts overlapping `cex_derivative_series` open-interest history points THEN conflict updates SHALL run only when `value_numeric`, `value_usd`, or `raw_payload_json` changed, SHALL report actual cursor row counts so unchanged replays count as zero writes, and SHALL not retain unconditional `DO UPDATE` write amplification or `written += 1` accounting.
- AC281. WHEN `CexDerivativeSeriesRepository` constructs `cex_derivative_series` series ids or upsert SQL parameters THEN it SHALL require non-empty formal `provider`, `exchange`, `native_market_id`, `metric`, and `period` identity before hash construction or SQL, SHALL normalize the hash inputs and SQL business-key values through the same repository boundary, and SHALL not retain empty-string identity compatibility through direct `provider.strip()`, `native_market_id.strip()`, `metric.strip()`, or `period.strip()` hash segments.
- AC282. WHEN `build_cex_detail_snapshot(...)` constructs `cex_detail_snapshots` current rows THEN exchange SHALL be a required explicit worker/provider input, the builder SHALL use that normalized exchange for `snapshot_id`, `exchange`, and CEX source refs, `CexOiRadarBoardWorker` SHALL pass `exchange="binance"` explicitly, and builder code SHALL not retain local `row.get("exchange") or "binance"`, hardcoded `cex-detail:binance`, or hardcoded `market:cex:binance` identity recovery.
- AC283. WHEN Token Case or Search Inspect returns a structured missing CEX detail block because `cex_detail_snapshots.latest_snapshot(...)` found no persisted row THEN the missing block SHALL keep `snapshot_id` and `exchange` absent/null, SHALL preserve target/native-market context and degraded reason, and SHALL not synthesize `cex-detail:binance:<native_market_id>` or `target.get("provider") or "binance"` read-path projection identity.
- AC284. WHEN `CexDetailSnapshotRepository` reads detail snapshots by target or market THEN `latest_snapshot(...)` SHALL require non-empty `target_type` and `target_id` before SQL, `latest_snapshot_by_market(...)` SHALL require non-empty `exchange` and `native_market_id` before SQL, and repository code SHALL not treat empty query identity as a PostgreSQL miss through direct `(target_type, target_id)` or `(exchange.lower(), native_market_id.upper())` parameters.
- AC285. WHEN `/api/cex/detail` receives target or market query params THEN the API route SHALL require paired non-empty `target_type`/`target_id` or non-empty `symbol` plus `exchange` before repository reads, SHALL reject partial or blank query identity with `invalid_cex_detail_query`, and SHALL not retain truthy `if target_type and target_id` / `elif symbol` branching or raw query-parameter repository calls that turn malformed input into `data: null`.
- AC286. WHEN `/api/cex/detail` receives both a complete target query and a complete market query THEN the API route SHALL reject the request with `invalid_cex_detail_query` before opening a repository session, SHALL require callers to choose exactly one lookup mode, and SHALL not retain target-first precedence that silently ignores `symbol`/`exchange` or any other competing query identity.
- AC287. WHEN `build_cex_detail_snapshot(...)` or `CexDetailSnapshotRepository` constructs, hashes, or upserts `cex_detail_snapshots` current rows THEN `quote_symbol` SHALL be a required non-empty writer output field, missing quote SHALL fail before snapshot payload hash or SQL, and builder/repository code SHALL not restore missing quote identity through `or "USDT"` defaults.
- AC288. WHEN `build_cex_detail_snapshot(...)` or `CexDetailSnapshotRepository` constructs, hashes, or upserts `cex_detail_snapshots` current rows THEN `base_symbol` SHALL be a required non-empty writer output field before serving-row payload or SQL, missing base SHALL fail before payload hash/upsert, and repository/builder code SHALL not restore missing base through empty-string defaults such as `snapshot.get("base_symbol") or ""`.
- AC289. WHEN `build_binance_oi_radar_rows(...)` consumes selected Binance universe routes for `cex_oi_radar_rows` THEN it SHALL require non-empty route `base_symbol` before Binance provider IO and board-row construction, SHALL fail malformed universe rows through the worker attempt-failure path instead of letting an empty base reach detail construction, and SHALL not retain empty-string route compatibility through `str(route.get("base_symbol") or "").strip().upper()`.
- AC290. WHEN `enrich_row_with_coinglass(...)` consumes a CEX board row for derivative/detail enrichment THEN it SHALL require non-empty row `base_symbol` before CoinGlass provider IO, SHALL classify missing base as malformed writer output rather than provider-unavailable data, and SHALL not retain empty-string compatibility or `coinglass_symbol_missing` degraded-state fallbacks.
- AC291. WHEN `CexDetailSnapshotRepository` hashes or upserts `cex_detail_snapshots` current rows THEN `status`, `baseline_status`, and `coinglass_status` SHALL be required formal writer-output enum fields before payload hash or SQL, missing or unknown status SHALL fail before serving-row writes, and repository code SHALL not restore missing states through `partial`, `missing`, or `unavailable` defaults.
- AC292. WHEN CEX CoinGlass enrichment is disabled, unconfigured, or bounded below the board row count THEN `enrich_rows_with_coinglass(...)` SHALL still emit a formal `coinglass_status="unavailable"` on each returned row, and `build_cex_detail_snapshot(...)` SHALL require a valid `coinglass_status` instead of restoring missing status through a builder-local `unavailable` default.
- AC293. WHEN `CexOiRadarRepository` hashes or upserts `cex_oi_radar_rows` current board rows THEN `base_symbol` and `quote_symbol` SHALL be required non-empty writer-output fields before payload hash or SQL, missing symbols SHALL fail before serving-row writes, and repository code SHALL not read `row["base_symbol"]` or `row["quote_symbol"]` directly without formal validation.
- AC294. WHEN `build_cex_detail_snapshot(...)` maps board OI delta values into detail snapshot period slots THEN the worker-selected `period` SHALL be a required non-empty input before mapping, missing period SHALL fail before snapshot construction, and builder code SHALL not restore missing period through `period or ""` or `unknown` degraded-reason compatibility.
- AC295. WHEN `CexDetailSnapshotRepository` hashes or upserts `cex_detail_snapshots` current rows THEN JSON list fields SHALL use only formal writer fields `level_bands`, `degraded_reasons`, and `source_refs`, writer input carrying legacy DB column aliases `level_bands_json`, `degraded_reasons_json`, or `source_refs_json` SHALL fail before SQL, and payload hash code SHALL not read those aliases as compatibility fallbacks.
- AC296. WHEN `build_cex_detail_snapshot(...)` consumes board/enrichment rows THEN level bands SHALL come only from formal `level_bands`, input carrying legacy storage alias `level_bands_json` SHALL fail before snapshot construction, and builder code SHALL not launder DB read-row shape back into the writer DTO.
- AC297. WHEN `CexOiRadarRepository` hashes or upserts `cex_oi_radar_rows` current board rows THEN each row SHALL carry formal `observed_at_ms` and `observed_at_source` (`provider` or `computed`) before payload hash or SQL, missing or unknown observation source SHALL fail before serving-row writes, and repository code SHALL not treat missing source as provider freshness or replace missing observed time with `computed_at`.
- AC298. WHEN `CexOiRadarRepository` hashes or upserts `cex_oi_radar_rows` current board rows THEN `score_components` SHALL be a required mapping-shaped scoring output before payload hash or SQL, missing or non-mapping components SHALL fail before serving-row writes, and repository code SHALL not restore missing components through `{}` defaults.
- AC299. WHEN `build_cex_detail_snapshot(...)` consumes board/enrichment rows THEN it SHALL require formal `observed_at_ms` and `observed_at_source` (`provider` or `computed`) before snapshot construction, missing or unknown observation source SHALL fail before source refs/status payloads are built, and builder code SHALL not infer source from `observed_at_ms == computed_at_ms`.
- AC300. WHEN `CexDetailSnapshotRepository` hashes or upserts a detail snapshot with `observed_at_ms` present THEN `observed_at_source` SHALL be required and limited to `provider` or `computed`, missing or unknown source SHALL fail before payload hash or SQL, and repository code SHALL not infer source from `observed_at_ms == computed_at_ms`.
- AC301. WHEN `CexDetailSnapshotRepository` hashes or upserts `cex_detail_snapshots` current rows THEN `level_bands`, `degraded_reasons`, and `source_refs` SHALL be present and list-shaped before payload hash or SQL, missing or non-list payload fields SHALL fail before serving-row writes, and repository code SHALL not restore missing list payloads through `[]` defaults.
- AC302. WHEN `CexDerivativeSeriesRepository` upserts `cex_derivative_series` history points THEN each point SHALL carry formal mapping-shaped `raw_payload` before JSONB SQL, missing or non-mapping raw payload SHALL fail before serving-row writes, and repository code SHALL not restore missing provider payload evidence through `{}` defaults.
- AC303. WHEN `CexDerivativeSeriesRepository` accounts for `cex_derivative_series` upsert writes THEN it SHALL require real `cursor.rowcount` evidence from the PostgreSQL driver, missing or invalid rowcount SHALL fail before returning write counts, and repository code SHALL not restore missing rowcount through default one-row accounting.
- AC304. WHEN `CexOiRadarRepository` accounts for `cex_oi_radar_rows` board delete/upsert writes THEN it SHALL require real `cursor.rowcount` evidence from the PostgreSQL driver, missing or invalid rowcount SHALL fail before returning write counts, and repository code SHALL not restore missing rowcount through default zero- or one-row accounting.
- AC305. WHEN `CexDetailSnapshotRepository` accounts for `cex_detail_snapshots` upsert writes THEN it SHALL require real `cursor.rowcount` evidence from the PostgreSQL driver, missing or invalid rowcount SHALL fail before returning write counts, and repository code SHALL not restore missing rowcount through default no-op accounting.
- AC306. WHEN `/api/cex/radar-board` shapes persisted CEX board rows THEN it SHALL require the repository payload to include formal `rows` and mapping-shaped `score_components_json` per row, malformed repository payloads SHALL fail instead of returning synthesized empty rows or empty score components, and route code SHALL not restore missing read-model fields through `[]` or `{}` defaults.
- AC307. WHEN `build_cex_detail_snapshot(...)` consumes `level_bands` from board/enrichment rows THEN each band SHALL be dict-shaped with non-empty `kind` and numeric `price` before snapshot/source-ref construction, malformed bands SHALL fail before snapshot output, and builder code SHALL not default missing kind to `level` or silently skip bands with missing price.
- AC308. WHEN CoinGlass enrichment or `build_cex_detail_snapshot(...)` carries present `degraded_reasons` from board/enrichment rows THEN those reasons SHALL be list-shaped with non-empty string items, malformed scalar strings, mappings, non-string items, or blank items SHALL fail before snapshot payload construction, and runtime code SHALL not restore malformed reasons through `list(row.get("degraded_reasons") or [])` or `_strings(...)` compatibility.
- AC309. WHEN `build_binance_oi_radar_rows(...)` consumes Binance provider ticker, funding, and OI-history sequences THEN returned provider objects SHALL expose the formal `CexOiTicker24h`, `CexFundingPremium`, and `CexOpenInterestPoint` fields before scoring/row construction, malformed objects SHALL fail instead of being restored to `None` metrics, and builder code SHALL not retain `_attr(...)` / `getattr(..., None)` object-reflection fallback or truthy `mark_price` fallback that overwrites valid zero values.
- AC310. WHEN runtime Binance OI provider wiring maps integration client ticker, funding, and OI-history rows into `CexOiTicker24h`, `CexFundingPremium`, and `CexOpenInterestPoint` THEN source integration objects SHALL expose the formal integration DTO fields before domain DTO construction, malformed objects SHALL fail instead of being restored to `None` metrics, and wiring code SHALL not retain `getattr(row, ..., None)` or empty-symbol defaults for those CEX OI fields.
- AC311. WHEN `MacroIntelRepository` hashes or upserts `macro_view_snapshots` current rows THEN formal JSON sections `panels_json`, `indicators_json`, `triggers_json`, `data_gaps_json`, `source_coverage_json`, `features_json`, `chain_json`, `scenario_json`, and `scorecard_json` SHALL be present and mapping/list-shaped as appropriate before payload hash or SQL, missing or malformed sections SHALL fail before serving-row writes, and repository code SHALL not restore missing snapshot sections through `{}` or `[]` defaults.
- AC312. WHEN `/api/macro` shapes a present `macro_view_snapshots` current row into the public Macro payload THEN formal JSON sections `panels_json`, `indicators_json`, `triggers_json`, `data_gaps_json`, `source_coverage_json`, `features_json`, `chain_json`, `scenario_json`, and `scorecard_json` SHALL be present and mapping/list-shaped as appropriate, malformed read-model rows SHALL fail instead of returning synthesized empty public sections, and route code SHALL not restore missing snapshot sections through `{}` or `[]` defaults.
- AC313. WHEN Macro module views shape a present `macro_view_snapshots` current row into `macro_module_view_v3` payloads THEN formal JSON sections `panels_json`, `indicators_json`, `triggers_json`, `data_gaps_json`, `source_coverage_json`, `features_json`, `chain_json`, `scenario_json`, and `scorecard_json` SHALL be present and mapping/list-shaped as appropriate, malformed read-model rows SHALL fail instead of returning synthesized empty module payloads, and module builder code SHALL not restore missing snapshot sections through `_mapping(snapshot.get(...))` or `_sequence(snapshot.get(...))` defaults.
- AC314. WHEN Token Radar rank-change fan-out, rank-input venue selection, or Token Capture Tier rank-set dirty hashing consumes current rows THEN resolved downstream target identity SHALL derive from formal `target_type_key` and `identity_id`, stale legacy `target_type` / `target_id` aliases SHALL not override those keys, alias-only current rows SHALL fail before dirty payload hashing or downstream enqueue, and Capture Tier rank-set payload hashes SHALL not restore missing formal identity from `target_type` / `target_id`.
- AC315. WHEN Token Radar generic target-dirty enqueue or source-dirty enqueue repositories receive dirty work rows THEN enqueue identity SHALL require formal `target_type_key` / `identity_id` and `source_event_id` where applicable before payload hash or queue SQL, legacy `target_type` / `target_id` / `intent_id` / `event_id` aliases SHALL not restore formal queue keys, and malformed rows SHALL fail instead of being silently skipped.
- AC316. WHEN `NewsRepository` writes `news_page_rows` from page projection rows THEN formal JSON sections `token_lanes`, `fact_lanes`, `story`, `token_impacts`, `content_tags`, `content_classification`, `source`, `signal`, `provider_rating`, `agent_brief`, `market_scope`, and `agent_admission` SHALL be present and list/mapping-shaped as appropriate before payload hash or SQL, malformed rows SHALL fail before serving-row writes, and repository code SHALL not restore missing page sections through `[]`, `{}`, or pending-agent defaults.
- AC317. WHEN `NewsRepository` reads a News item detail and a current `news_page_rows` row exists THEN public projected fields SHALL be read from that page row only, missing or malformed projected text/mapping/list fields SHALL fail with `news_item_detail_projection_required:*` or `news_item_detail_projection_invalid:*`, and raw `news_items`, empty JSON defaults, or `projection_missing` signal fallback SHALL NOT repair projected story, market, signal, provider, content, lane, or agent-admission fields.
- AC318. WHEN `NewsRepository` lists News page rows or high-signal notification candidates from `news_page_rows` THEN the selected projected text/mapping/list fields SHALL be validated before public or notification shaping, malformed rows SHALL fail with `news_page_row_projection_required:*` or `news_page_row_projection_invalid:*`, and list/candidate code SHALL NOT downgrade malformed `agent_brief_json` to pending state or return unvalidated projected JSON sections.
- AC319. WHEN `TokenProfileReadModel` shapes a present `token_profile_current` row for public profile reads THEN formal current-row fields `status`, `source_kind`, `quality_flags_json`, and `source_payload_json` SHALL be present and correctly shaped, malformed rows SHALL fail with `token_profile_current_public_required:*` or `token_profile_current_public_invalid:*`, and read-model code SHALL NOT downgrade malformed present rows to pending state, empty flags, or empty source payloads.
- AC320. WHEN `SignalPulseService` shapes a present `pulse_candidates` row for public or hidden list/detail payloads THEN `decision_json` SHALL be mapping-shaped and `gate_reasons_json`, `risk_reasons_json`, `evidence_event_ids_json`, and `source_event_ids_json` SHALL be list-shaped, malformed rows SHALL fail with `signal_pulse_public_candidate_required:*` or `signal_pulse_public_candidate_invalid:*`, and public mapper code SHALL NOT repair malformed candidate JSON into empty decision text or empty arrays.
- AC321. WHEN `EventTokenProjectionQuery` shapes selected current `token_intent_resolutions` rows for `/api/recent`, WebSocket replay/live, or watchlist timelines THEN `resolution_id`, `intent_id`, `event_id`, and `resolution_status` SHALL be non-empty text and `reason_codes_json`, `candidate_ids_json`, and `lookup_keys_json` SHALL be list-shaped JSONB values, malformed rows SHALL fail with `event_token_projection_required:*` or `event_token_projection_invalid:*`, and the public projection SHALL NOT repair missing identity/status or malformed JSON arrays through empty strings, `json.loads`, or `[]` defaults.
- AC322. WHEN `TokenRadarProjection` shapes selected rank-source rows into `token_radar_current_rows` THEN `resolution_status` SHALL be non-empty text and `reason_codes_json`, `candidate_ids_json`, and `lookup_keys_json` SHALL be list-shaped JSONB values before `resolution_json` or unresolved serving identity construction, malformed rows SHALL fail with `token_radar_projection_resolution_required:*`, `token_radar_projection_resolution_invalid:*`, or `token_radar_projection_identity_required`, and projection code SHALL NOT repair missing resolution fields through `"NIL"`, `[]`, or display-symbol-derived `LookupKey` identity.
- AC323. WHEN `TokenRadarProjection` classifies a selected rank-source row as resolved for `token_radar_current_rows` THEN high-confidence `EXACT` / `UNIQUE_BY_CONTEXT` resolution rows SHALL carry non-empty formal `target_type` and `target_id`, `target_type` SHALL be limited to `Asset` or `CexToken`, malformed rows SHALL fail with `token_radar_projection_resolved_target_required:*` or `token_radar_projection_resolved_target_invalid:*`, and projection code SHALL NOT downgrade malformed high-confidence target identity into attention or infer resolved state through truthy `target_id` checks.
- AC324. WHEN `TokenRadarProjection` builds a resolved `Asset` target payload for `token_radar_current_rows` THEN the joined `asset_identity_current` fields `asset_identity_confidence`, `asset_identity_reason_codes`, and `asset_identity_conflict_count` SHALL be present with non-empty text, list, and non-negative integer shapes respectively, malformed rows SHALL fail with `token_radar_projection_asset_identity_required:*` or `token_radar_projection_asset_identity_invalid:*`, and projection code SHALL NOT repair missing identity-current evidence through empty reason arrays, zero conflicts, or target-local `NIL` status defaults.
- AC325. WHEN Token Radar builds source requests, rank-source repair target payloads, or latest-market-context target payloads THEN each target SHALL carry formal `target_type_key` and `identity_id` before request generation, JSONB target SQL, source-edge repair, or target-feature delete/upsert, malformed rows SHALL fail with `token_radar_projection_target_identity_required:*` or `token_radar_rank_source_target_identity_required:*`, and helper code SHALL NOT restore target identity from legacy `target_type` / `target_id` aliases or silently skip missing formal target identity.
- AC326. WHEN `TokenRadarProjection` converts projection-private `token_radar_target_features` rows into `token_radar_current_rows` THEN each target-feature row SHALL carry formal `target_type_key` and `identity_id` before row-id/current-row construction, malformed rows SHALL fail with `token_radar_current_identity_required`, and `_row_from_target_feature(...)` SHALL NOT manufacture empty serving keys or restore formal identity from legacy `target_type` / `target_id`.
- AC327. WHEN `TokenRadarProjection` converts projection-private `token_radar_target_features` rows into `token_radar_current_rows` THEN target-feature row-id dimensions `projection_version`, `window`, `scope`, and `lane` SHALL be non-empty, `latest_event_received_at_ms` SHALL be a non-negative integer, and `factor_snapshot_json` SHALL be a non-empty mapping before current-row construction, malformed rows SHALL fail with `token_radar_target_feature_current_row_required:*` or `token_radar_target_feature_current_row_invalid:*`, and `_row_from_target_feature(...)` SHALL NOT repair missing target-feature control fields through empty row-id segments, `attention` lane defaults, zero source frontiers, or empty factor snapshots.
- AC328. WHEN `TokenRadarProjection` filters and selects rank inputs for rank-set publication THEN each rank input SHALL expose non-negative integer `latest_event_received_at_ms` before freshness filtering and known `lane` (`resolved` or `attention`) before lane selection, malformed rank inputs SHALL fail with `token_radar_rank_input_required:*` or `token_radar_rank_input_invalid:*`, and rank-set selection SHALL NOT repair missing latest event time through `0` or silently drop missing/unknown lane rows from both publication lanes.
- AC329. WHEN `TokenRadarProjection` converts projection-private `token_radar_target_features` rows into `token_radar_current_rows` THEN current-row `created_at_ms` SHALL derive from formal non-negative integer `last_scored_at_ms`, malformed rows SHALL fail with `token_radar_target_feature_current_row_required:last_scored_at_ms` or `token_radar_target_feature_current_row_invalid:last_scored_at_ms`, and `_row_from_target_feature(...)` SHALL NOT repair missing scoring time through target-feature `updated_at_ms` or the runtime wall clock.
- AC330. WHEN `TokenRadarRepository` writes projection-private `token_radar_target_features` rows THEN projection payload fields `lane`, `source_max_received_at_ms`, `source_event_ids_json`, `created_at_ms`, and `factor_snapshot_json` SHALL be present with formal scalar/list/mapping shapes before payload hash or SQL, malformed rows SHALL fail with `token_radar_target_feature_payload_required:*` or `token_radar_target_feature_payload_invalid:*`, and `_target_feature_payload(...)` SHALL NOT repair malformed projection output through `attention`, `computed_at_ms`, `[]`, or `{}` defaults.
- AC331. WHEN Token Radar validates or writes v3 `factor_snapshot_json` THEN `composite.rank_score`, `composite.recommended_decision`, and `gates.max_decision` SHALL be present with formal numeric/decision shapes before target-feature payload hash or SQL, malformed snapshots SHALL fail with `factor_snapshot_json.* is required` or `token_radar_target_feature_payload_required/invalid:*`, and contract/writer code SHALL NOT repair missing score or decision output through `0.0`, `raw_alpha_score`, or `discard` defaults.
- AC332. WHEN `TokenRadarProjection` ranks compact `token_radar_target_features` inputs for rank-set publication THEN compact inputs SHALL expose formal `raw_composite_score` and `gates_max_decision`, ranked rows SHALL expose formal `rank_score` and `recommended_decision`, malformed rows SHALL fail with `token_radar_rank_input_required:*` or `token_radar_rank_input_invalid:*`, and compact ranking/sort/decision helpers SHALL NOT repair missing score, gate cap, or ranked decision through `0.0` or `discard` defaults.
- AC333. WHEN `settle_token_factor_scores(...)` settles historical Token Radar rows into `token_score_evaluations` THEN each row SHALL carry a formal v3 `factor_snapshot_json` with `composite.rank_score`, malformed snapshots SHALL fail with `factor_snapshot_json.* is required` before market lookup or bucket upsert, and evaluation code SHALL NOT repair missing or invalid rank score through `0.0` or place malformed rows in the `0-19` bucket.
- AC334. WHEN `settle_token_factor_scores(...)` derives settlement identity and market-tick targets from a historical Token Radar row THEN the settlement consumer SHALL require `factor_snapshot_json.subject.target_type` and `.target_id`, malformed settlement subjects SHALL fail with `factor_snapshot_json.subject.* is required` before market lookup or bucket upsert, and evaluation code SHALL NOT repair subject identity from current-row top-level `target_type` / `target_id` or re-read `row.get("factor_snapshot_json")` after formal validation.
- AC335. WHEN `settle_token_factor_scores(...)` derives settlement timestamps for market lookup, exit windows, sample ranges, and daily IC grouping THEN it SHALL use formal `factor_snapshot_json.provenance.computed_at_ms`, malformed provenance time SHALL fail through the v3 snapshot contract, and evaluation code SHALL NOT repair missing top-level row time through `row.get("computed_at_ms") or 0` or epoch-zero settlement time.
- AC336. WHEN `settle_token_factor_scores(...)` computes family rank IC and family coverage diagnostics from a historical Token Radar row THEN it SHALL read formal v3 `factor_snapshot_json.families.<family>.score`, malformed family score payloads SHALL fail through the v3 snapshot contract, and evaluation code SHALL NOT repair or source family diagnostics from optional `composite.family_scores` aliases.
- AC337. WHEN `settle_token_factor_scores(...)` derives CEX settlement market-tick targets from a historical Token Radar row THEN CEX market identity SHALL come only from `factor_snapshot_json.subject.provider` and `.native_market_id`, missing fields SHALL become `missing_market_target` before market lookup, and evaluation code SHALL NOT repair CEX settlement identity from `market.decision_latest.provider`, `subject.instrument`, or whole-snapshot re-reading.
- AC338. WHEN `settle_token_factor_scores(...)` derives settlement subject identity THEN `factor_snapshot_json.subject.target_type` SHALL be formal `Asset` or `CexToken`, direct market-tick target types `chain_token` / `cex_symbol` SHALL fail with `factor_snapshot_json.subject.target_type is invalid` before market lookup or bucket upsert, and evaluation code SHALL NOT pass direct market-tick subject ids through to `latest_at_or_before(...)` or `first_between(...)`.
- AC339. WHEN `settle_token_factor_scores(...)` derives Asset settlement market-tick targets from a historical Token Radar row THEN Asset market identity SHALL come only from `factor_snapshot_json.subject.chain` and `.address`, missing fields SHALL become `missing_market_target` before market lookup, and evaluation code SHALL NOT repair Asset settlement identity from `subject.chain_id` or `subject.asset_address`.
- AC340. WHEN Token Radar projection ranks current rows for publication THEN it SHALL use compact rank inputs and `_compact_rank_key`, SHALL not retain retired snapshot-row `_rank_key` / `_display_score_from_value` / `_factor_snapshot_for_ranking` / `_raw_composite_score` helpers, and SHALL not keep `raw_alpha_score` fallback or invalid-snapshot demotion as compatibility ranking paths.
- AC341. WHEN Token Radar projection patches ranked compact rows into current rows THEN ranked-row metadata `normalization_status`, `cohort_status`, `cohort_size`, `cohort_metadata`, `factor_ranks`, `rank`, `rank_score`, `recommended_decision`, and `latest_event_received_at_ms` SHALL be present with formal shapes before current-row or `factor_snapshot_json` mutation, malformed rows SHALL fail with `token_radar_ranked_row_required/invalid:*` or `token_radar_rank_input_required/invalid:*`, and patch code SHALL NOT repair missing ranked metadata through `no_signal`, `not_ranked`, empty factor-rank maps, rank `0`, source watermark `0`, or direct `ranked.get(...)` writes.
- AC342. WHEN Token Radar projection patches ranked normalization payloads into current rows THEN `cohort_in_cohort` and `alpha_rank` SHALL be present with formal normalization semantics, `factor_ranks` SHALL contain exactly every Token Radar factor family with each rank either `None` or a bounded `0..1` number, `normalization_status = no_signal` SHALL require `alpha_rank = None`, `normalization_status = ranked` SHALL require numeric `alpha_rank`, malformed rows SHALL fail with `token_radar_ranked_row_required/invalid:*`, and patch code SHALL NOT repair missing cohort membership to `False`, missing alpha rank to `None`, incomplete rank maps to no-op family scores, or arbitrary rank values through `float(rank)`.
- AC343. WHEN `TokenRadarRepository` accounts for `token_radar_current_rows` delete/upsert writes or projection-private `token_radar_target_features` write/delete/retention writes THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before returning publication or cache write counts, and repository code SHALL not restore missing rowcount through default zero- or one-row accounting.
- AC344. WHEN Token Radar target-dirty or source-dirty queue repositories account for queue enqueue, completion, retry, or repair/catch-up writes THEN they SHALL require real PostgreSQL `cursor.rowcount` evidence for mutation paths that return changed-row counts, missing or invalid rowcount SHALL fail before returning queue write counts, and repository code SHALL not restore missing rowcount through default zero-row accounting.
- AC345. WHEN Token Radar rank-source edge population or prune paths account for `token_radar_rank_source_events` mutations THEN populate paths SHALL require explicit SQL aggregate count rows for upsert/delete counts, prune paths SHALL require PostgreSQL `cursor.rowcount`, missing or invalid mutation-count evidence SHALL fail before returning changed-row counts, and query code SHALL not restore missing count evidence through empty result rows or default zero-row accounting.
- AC346. WHEN Pulse trigger dirty-target completion paths account for done, error, or reschedule mutations THEN they SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before returning dirty-trigger changed-row counts, and repository code SHALL not restore missing rowcount through default zero-row accounting.
- AC347. WHEN Narrative Admission dirty-target completion paths account for done, error, or reschedule mutations THEN they SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before returning dirty-target changed-row counts, and repository code SHALL not restore missing rowcount through default zero-row accounting.
- AC348. WHEN News projection dirty-target completion paths account for done or error mutations THEN they SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before returning dirty-target changed-row counts, and repository code SHALL not restore missing rowcount through default zero-row accounting.
- AC349. WHEN `NotificationRepository` decides whether `INSERT ... DO NOTHING` created a `notifications` fact row or insert-only `notification_deliveries` control row THEN it SHALL require real PostgreSQL single-row `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before fact/control state is classified, and repository code SHALL not use bare `cursor.rowcount == 0` or default rowcount compatibility to decide created-vs-existing state.
- AC350. WHEN `SignalRepository` decides whether `INSERT ... DO NOTHING` created an `account_token_alerts` watched-account alert fact THEN it SHALL require real PostgreSQL single-row `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before alert state is classified, and repository code SHALL not use bare `cursor.rowcount == 0` or default rowcount compatibility to decide created-vs-existing state.
- AC351. WHEN `ProjectionRepository.mark_stale_running_runs(...)` accounts for abandoned `projection_runs` THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before abandoned-run counts are returned, and repository code SHALL not restore missing rowcount through default zero-run accounting.
- AC352. WHEN `NewsRepository` accounts for ordinary item lifecycle, source-quality status, or page-row changed-row mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-row accounting.
- AC353. WHEN `AssetProfileRefreshTargetRepository` accounts for `asset_profile_refresh_targets` reschedule or error completion mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-target accounting.
- AC354. WHEN `TokenProfileCurrentDirtyTargetRepository` accounts for `token_profile_current_dirty_targets` done or error completion mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-target accounting.
- AC355. WHEN `MarketTickCurrentDirtyTargetRepository` accounts for `market_tick_current_dirty_targets` done or error completion mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-target accounting.
- AC356. WHEN `TokenImageSourceDirtyTargetRepository` accounts for `token_image_source_dirty_targets` done or error completion mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-target accounting.
- AC357. WHEN `TokenCaptureTierDirtyTargetRepository` accounts for `token_capture_tier_dirty_targets` enqueue or done mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-target accounting.
- AC358. WHEN `TokenCaptureTierRepository` demotes hot `token_capture_tier` rows outside the active rank set THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before demotion counts are returned, and repository code SHALL not restore missing rowcount through default zero-demotion accounting.
- AC359. WHEN `DiscoveryRepository` accounts for `token_discovery_dirty_lookup_keys` enqueue, done, or reschedule mutations THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed-row counts are returned, and repository code SHALL not restore missing rowcount through default zero-lookup accounting.
- AC360. WHEN `EnrichedEventRepository` attaches a backfilled event anchor or marks a pending anchor terminal THEN it SHALL require real PostgreSQL single-row `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before lifecycle state is classified, and repository code SHALL not restore missing rowcount through default no-op accounting.
- AC361. WHEN `MacroIntelRepository` accounts for macro sync-window terminal/retry/fail writes, `macro_sync_state` repair, `macro_projection_dirty_targets` enqueue/done/error writes, or `macro_observation_series_rows` delete/upsert writes THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, single-row paths SHALL reject multi-row rowcount, missing or invalid rowcount SHALL fail before write counts are returned, and repository code SHALL not restore missing rowcount through default zero/one/length accounting.
- AC362. WHEN `NarrativeRepository` accounts for `narrative_admissions` upsert or stale-delete writes THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed admission counts are returned, and repository code SHALL not restore missing rowcount through default zero-admission accounting.
- AC363. WHEN `PulseJobsRepository` accounts for stale `pulse_agent_runs` timeout cleanup THEN it SHALL require real PostgreSQL `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before changed run counts are returned, and repository code SHALL not restore missing rowcount through default zero-run accounting.
- AC364. WHEN `EvidenceRepository` or `EntityRepository` accounts for `raw_frames`, `events`, or `event_entities` `INSERT ... DO NOTHING` writes THEN it SHALL require PostgreSQL single-row `cursor.rowcount` evidence, missing or invalid rowcount SHALL fail before created-vs-existing state or inserted-entity counts are returned, and repository code SHALL not classify fact writes through bare rowcount comparisons or default rowcount compatibility.
- AC365. WHEN CEX read-model repositories account for `cex_oi_radar_rows`, `cex_detail_snapshots`, or `cex_derivative_series` write counts THEN they SHALL require PostgreSQL `cursor.rowcount` to be a non-boolean non-negative integer, missing, boolean, negative, or non-integer rowcount SHALL fail before write counts are returned, and repository code SHALL not restore malformed rowcount through `int(rowcount)` or `max(..., 0)` compatibility.
- AC366. WHEN Token Radar current-row, target-feature, target/source dirty queue, or rank-source prune paths account for changed-row counts THEN cursor rowcount evidence SHALL be a non-boolean non-negative integer, numeric strings SHALL fail as malformed driver evidence before write counts are returned, and repository/query code SHALL not restore malformed cursor rowcount through `int(rowcount)` compatibility.
- AC367. WHEN `NotificationRepository` writes notification read markers through `mark_read`, `mark_all_read`, or `mark_author_read` THEN PostgreSQL cursor rowcount evidence SHALL be required before success or changed-row counts are returned, bulk read-marker counts SHALL come from a single `INSERT ... SELECT ... RETURNING` cursor whose rowcount matches returned rows, and repository code SHALL not restore read-marker accounting through `return len(rows)` or default rowcount compatibility.
- AC368. WHEN Token Radar target/source dirty generic enqueue paths account for `token_radar_dirty_targets` or `token_radar_source_dirty_events` mutations THEN changed-row counts SHALL come from PostgreSQL `cursor.rowcount`, missing or invalid rowcount SHALL fail before enqueue counts are returned, and repository code SHALL not restore enqueue accounting through candidate `len(records)`.
- AC369. WHEN News projection dirty-target enqueue accounts for `news_projection_dirty_targets` mutations THEN changed-row counts SHALL come from PostgreSQL `cursor.rowcount`, missing or invalid rowcount SHALL fail before enqueue counts are returned, and repository code SHALL not restore enqueue accounting through candidate `len(records)`.
- AC370. WHEN Market Tick Current dirty-target enqueue accounts for `market_tick_current_dirty_targets` mutations THEN changed-row counts SHALL come from PostgreSQL `cursor.rowcount`, missing or invalid rowcount SHALL fail before enqueue counts are returned, and repository code SHALL not restore enqueue accounting through candidate `len(records)`.
- AC371. WHEN Token Radar first-seen upsert accounts for `token_radar_target_first_seen` mutations THEN changed-row counts SHALL come from PostgreSQL `cursor.rowcount`, missing or invalid rowcount SHALL fail before first-seen write counts are returned, and repository code SHALL not restore first-seen accounting through candidate `len(records)` or `len(rows)`.
- AC372. WHEN `PulseJobsRepository` terminalizes stale or exhausted `pulse_agent_jobs` through `UPDATE ... RETURNING` batches THEN cursor rowcount SHALL be required before terminal ledger writes, rowcount SHALL match returned rows, missing or invalid rowcount SHALL fail before terminalized-job counts are returned, and repository code SHALL not restore terminalization accounting through `return len(rows)` or `terminalized += len(rows)`.
- AC373. WHEN `NewsProjectionDirtyTargetRepository` terminalizes claimed `news_projection_dirty_targets` through delete-returning batches THEN cursor rowcount SHALL be required before terminal ledger writes, rowcount SHALL match returned deleted rows, missing or invalid rowcount SHALL fail before terminal counts are returned, and repository code SHALL not restore terminalization accounting through `return len(deleted_records)` or `return len(rows)`.
- AC374. WHEN `NewsRepository` disables unconfigured `news_sources` through `UPDATE ... RETURNING` source reconcile paths THEN cursor rowcount SHALL be required, rowcount SHALL match returned disabled source rows, missing or invalid rowcount SHALL fail before disable counts or reconcile rows are returned, and repository code SHALL not restore disable accounting through `return len(rows)`.
- AC375. WHEN `DiscoveryRepository` terminalizes claimed `token_discovery_dirty_lookup_keys` through `DELETE ... RETURNING` lookup-claim batches THEN cursor rowcount SHALL be required before terminal ledger writes, rowcount SHALL match returned deleted lookup rows, missing or invalid rowcount SHALL fail before terminal counts are returned, and repository code SHALL not restore terminalization accounting through `len(deleted_rows)` or returned-row length.
- AC376. WHEN `RegistryRepository` deactivates missing `us_equity_symbols` through `UPDATE ... RETURNING symbol` THEN cursor rowcount SHALL be required, rowcount SHALL match returned inactive symbol rows, missing or invalid rowcount SHALL fail before deactivation counts are returned, and repository code SHALL not restore deactivation accounting through `return len(row)`, `return len(rows)`, or returned-row length.
- AC377. WHEN `TokenImageAssetRepository` writes `token_image_assets` pending, ready, error, or unsupported lifecycle state THEN PostgreSQL cursor rowcount SHALL be required as single-row DML evidence, pending/ready `RETURNING` paths SHALL require rowcount to match returned row presence before affected counts or rows are returned, missing or invalid rowcount SHALL fail before lifecycle results are reported, and repository code SHALL not restore pending affected counts through `row is not None` or `affected += 1`.
- AC378. WHEN `EventAnchorBackfillJobRepository` claims, completes, terminalizes, retries, reconciles, expires, fails, or reschedules `event_anchor_backfill_jobs` through `UPDATE ... RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned rows, single-row CAS paths SHALL only accept 0/1 rowcount, missing or invalid rowcount SHALL fail before claim rows, terminal ledger writes, retry rows, reconcile counts, or booleans are reported, and repository code SHALL not restore lifecycle accounting through `row is not None`, returned-row presence, or `len(updated_rows)`.
- AC379. WHEN `TokenProfileCurrentRepository` writes the public `token_profile_current` current row through `INSERT ... ON CONFLICT ... RETURNING true AS changed` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, only 0/1 rowcount SHALL be valid, missing or invalid rowcount SHALL fail before changed booleans or worker `rows_written` are reported, and repository code SHALL not restore changed accounting through optional `fetchone` probing or returned-row presence alone.
- AC380. WHEN `MarketTickCurrentRepository` writes the public `market_tick_current` current row through `INSERT ... ON CONFLICT ... RETURNING true AS changed` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, only 0/1 rowcount SHALL be valid, missing or invalid rowcount SHALL fail before changed booleans, downstream dirty enqueue decisions, wake decisions, or worker write counts are reported, and repository code SHALL not restore changed accounting through returned-row presence alone.
- AC381. WHEN `TokenCaptureTierRepository` writes the rebuildable `token_capture_tier` capture-control projection through `INSERT ... ON CONFLICT ... RETURNING true AS changed` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, only 0/1 rowcount SHALL be valid, missing or invalid rowcount SHALL fail before changed booleans or worker `rows_written` are reported, and repository code SHALL not restore changed accounting through returned-row presence alone.
- AC382. WHEN `IdentityEvidenceRepository` writes the deterministic `asset_identity_current` current identity row through `INSERT ... ON CONFLICT ... RETURNING true AS changed` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, only 0/1 rowcount SHALL be valid, missing or invalid rowcount SHALL fail before changed booleans or identity recompute `rows_written` are reported, and repository code SHALL not restore changed accounting through optional `fetchone` probing or returned-row presence alone.
- AC383. WHEN `MacroIntelRepository` writes `macro_view_snapshots` or `macro_daily_briefs` current rows through `INSERT ... ON CONFLICT ... RETURNING true AS changed` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, only 0/1 rowcount SHALL be valid, missing or invalid rowcount SHALL fail before snapshot changed booleans, downstream wakes, daily-brief writes, or worker `rows_written` are reported, and repository code SHALL not restore changed accounting through `dict(row or {})` or returned-row presence alone.
- AC384. WHEN `NewsRepository._delete_zero_edge_news_item` removes old zero-edge `news_items` after canonical edge remap through `DELETE ... RETURNING` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned-row presence, missing or invalid rowcount SHALL fail before cleanup booleans are returned, and repository code SHALL not restore delete accounting through `return row is not None` or returned-row presence alone.
- AC385. WHEN `terminalize_source_row` writes `worker_queue_terminal_events` through `INSERT ... ON CONFLICT ... RETURNING *` or `resolve_terminal_event` writes operator actions through `UPDATE ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, missing or invalid rowcount SHALL fail before terminal ledger rows, operator payloads, or retry transitions are reported, and platform code SHALL not restore terminal accounting through returned-row presence alone.
- AC386. WHEN `src/parallax/app/runtime/job_queue.py` names `pulse_agent_jobs` or `notification_deliveries` for ops diagnostics THEN that module SHALL expose descriptor metadata only, SHALL NOT define a generic `JobQueue` / `BackoffPolicy` executor or `claim_batch` / `finalize_success` / `finalize_failure` / `reclaim_stale` DML helpers, and domain repositories SHALL remain the only runtime owners of those queue state transitions.
- AC387. WHEN `PulseAdmissionRepository` writes Pulse edge state or candidate edge budgets through single-row `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, required upsert paths SHALL fail when no row is returned, missing or invalid rowcount SHALL fail before edge rows, budget booleans, or admission state are reported, and repository code SHALL not restore success classification through `row is not None` or returned-row presence alone.
- AC388. WHEN `PulsePlaybooksRepository` writes Pulse playbook snapshots or outcomes through `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, snapshot no-change writes SHALL return no row only when rowcount is 0, changed snapshot and outcome writes SHALL require rowcount=1 with a returned row, missing or invalid rowcount SHALL fail before playbook rows are returned, and repository code SHALL not restore snapshot success through fallback `SELECT` or returned-row presence alone.
- AC389. WHEN `PulseCandidatesRepository` writes public Pulse candidate rows or hides low-information candidates through `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, unchanged candidate upserts and no-op hide attempts SHALL return no row only when rowcount is 0, changed candidate writes SHALL require rowcount=1 with a returned row, missing or invalid rowcount SHALL fail before candidate rows are returned, and repository code SHALL not restore candidate success through fallback `SELECT` or returned-row presence alone.
- AC390. WHEN `PulseRunsRepository` writes Pulse agent runs or run steps through `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, required insert/upsert audit paths SHALL require rowcount=1 with a returned row, `finish_agent_run` SHALL validate rowcount against returned-row presence after the run existence check, missing or invalid rowcount SHALL fail before run or step audit rows are returned, and repository code SHALL not restore agent audit success through returned-row presence alone.
- AC391. WHEN `PulseAgentEvalRepository` writes agent runtime versions, eval cases, or eval results through `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, each required audit write SHALL require rowcount=1 with a returned row, missing or invalid rowcount SHALL fail before eval audit rows are returned, and repository code SHALL not restore eval audit success through returned-row presence alone.
- AC392. WHEN `PulseEvidenceRepository.upsert_packet(...)` persists a sealed Pulse evidence packet through `RETURNING evidence_packet_id` THEN PostgreSQL cursor rowcount SHALL be required, the packet write SHALL require rowcount=1 with a returned row before `pulse_agent_runs` is linked to the packet id/hash, missing or invalid rowcount SHALL fail before run-link updates, and repository code SHALL not restore evidence-packet success through returned-row presence alone.
- AC393. WHEN `CexTokenProfileRepository.upsert_ready_profile_if_token_exists(...)` writes Binance CEX profile source-cache rows through `INSERT ... SELECT ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, no-existing-token outcomes SHALL be rowcount=0 with no row, refreshed source-cache writes SHALL be rowcount=1 with a returned row, and repository code SHALL not restore CEX source-cache success through returned-row presence alone.
- AC394. WHEN `MarketTickRepository` appends `market_ticks` through `INSERT ... DO NOTHING RETURNING tick_id` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, created tick outcomes SHALL be rowcount=1 with a returned `tick_id`, dedupe-conflict outcomes SHALL be rowcount=0 with no row, and repository code SHALL not restore append-only market fact success or duplicate classification through returned-row presence alone.
- AC395. WHEN `NotificationRepository` requeues or claims `notification_deliveries` through `RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, no-op/no-delivery outcomes SHALL be rowcount=0 with no row, reactivated or claimed delivery outcomes SHALL be rowcount=1 with a returned row, and repository code SHALL not restore delivery state-machine success through returned-row presence alone.
- AC396. WHEN `MacroIntelRepository` enqueues or claims `macro_sync_windows` through `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required, enqueue SHALL require rowcount=1 with a returned `sync_window_id`, claim/no-work outcomes SHALL be valid only as rowcount=0 with no row or rowcount=1 with a returned window row, and repository code SHALL not restore Macro sync-window state-machine success through returned-row presence or `dict(row or {})` alone.
- AC397. WHEN `NewsRepository` writes `news_page_rows` through `INSERT ... ON CONFLICT ... RETURNING (xmax = 0)` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL be valid 0/1 and match returned-row presence, unchanged projections SHALL be valid only as rowcount=0 with no row, inserted/updated serving-row changes SHALL be rowcount=1 with a returned row, and repository code SHALL not restore page-row changed accounting through returned-row presence alone.
- AC398. WHEN `NewsRepository.claim_due_sources(...)` claims due `news_sources` through `UPDATE ... RETURNING sources.*` THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned claim rows, rowcount=0 with no rows SHALL be the only no-work result, missing or invalid rowcount SHALL fail before due source rows are returned to `NewsFetchWorker`, and repository code SHALL not restore source-claim success through chained `.fetchall()` or returned-list length alone.
- AC399. WHEN `NewsRepository.finish_fetch_run(...)` finalizes `news_fetch_runs` through `UPDATE ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required as a required single-row result, rowcount=1 with a returned row SHALL be the only valid finalized-run result, no-row/missing/invalid/mismatched rowcount SHALL fail before `news_sources` status is updated, and repository code SHALL not restore fetch-run success through chained `.fetchone()` or `dict(row)`.
- AC400. WHEN `NewsRepository.start_fetch_run(...)` starts a News fetch run THEN PostgreSQL cursor rowcount SHALL be required for both the `news_fetch_runs` running-row insert and the matching `news_sources` last-fetch update, each SHALL require rowcount=1, insert rowcount failures SHALL occur before source state is updated, source-update rowcount failures SHALL occur before a run id is returned, and repository code SHALL not restore fetch-run start success through unverified `execute(...)` calls or rowcount defaults.
- AC401. WHEN `NewsRepository.upsert_source(...)` reconciles configured `news_sources` through `INSERT ... ON CONFLICT ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required as a required single-row result, rowcount=1 with a returned source row SHALL be the only valid inserted/updated source result, no-row/missing/invalid/mismatched rowcount SHALL fail before inserted/updated source rows are returned, and repository code SHALL not restore source-upsert success through chained `.fetchone()` or `dict(row)`.
- AC402. WHEN `NewsRepository.upsert_provider_item(...)` persists `news_provider_items` through `INSERT ... ON CONFLICT ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required as a required single-row result, rowcount=1 with a returned provider-item row SHALL be the only valid inserted/updated provider observation result, no-row/missing/invalid/mismatched rowcount SHALL fail before inserted/updated provider observations are returned to fetch accounting, and repository code SHALL not restore provider-item upsert success through chained `.fetchone()` or `dict(row)`.
- AC403. WHEN `NewsRepository.upsert_canonical_news_item(...)` persists canonical `news_items` through `INSERT ... ON CONFLICT ... RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required as a required single-row result, rowcount=1 with a returned canonical item row SHALL be the only valid inserted/updated canonical fact result, no-row/missing/invalid/mismatched rowcount SHALL fail before observation edges, remap cleanup, or affected-item accounting use the canonical `news_item_id`, and repository code SHALL not restore canonical item upsert success through chained `.fetchone()` or returned-row presence alone.
- AC404. WHEN `NewsRepository.upsert_canonical_news_item(...)` persists `news_item_observation_edges` through `INSERT ... ON CONFLICT` THEN PostgreSQL cursor rowcount SHALL be required, rowcount=1 SHALL be the only valid observation-edge link result, missing/invalid/zero/multi-row rowcount SHALL fail before provider-article remap, material duplicate remap, summary refresh, or affected-item accounting treats the provider observation as linked, and repository code SHALL not restore edge-upsert success through unverified `self.conn.execute(...)` or rowcount-default compatibility.
- AC405. WHEN `NewsRepository` refreshes observation summary aggregates through `UPDATE news_items` / `RETURNING items.*` THEN PostgreSQL cursor rowcount SHALL be required, rowcount=1 with a returned current item row SHALL be the only valid required summary-refresh result before affected-item accounting uses refreshed source/provider-article aggregates, old zero-edge cleanup MAY accept rowcount=0 with no returned row only through an explicit optional path, and repository code SHALL not restore summary state through fallback `SELECT` readback or returned-row presence alone.
- AC406. WHEN `NewsRepository` remaps provider-article or material-duplicate observation edges through `news_item_observation_edges` CTEs that return old item ids THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned old item-id rows, missing/invalid/mismatched rowcount SHALL fail before old-item summary cleanup, dirty-target remap, zero-edge cleanup, or affected-item accounting uses those old ids, and repository code SHALL not restore remap success through chained `.fetchall()`, returned-list length, or direct returned-row presence alone.
- AC407. WHEN `NewsRepository` inserts `news_item_agent_runs` or upserts current `news_item_agent_briefs` through `RETURNING *` THEN PostgreSQL cursor rowcount SHALL be required as a required single-row result, rowcount=1 with a returned row SHALL be the only valid agent audit/current brief write result, no-row/missing/invalid/mismatched rowcount SHALL fail before page dirty fan-out, publication eligibility, or returned audit/current rows are reported, and repository code SHALL not restore agent write success through chained `.fetchone()` or `dict(row)`.
- AC408. WHEN `NewsRepository` reselects an old `news_items` representative from remaining observation edges through `UPDATE news_items ... RETURNING items.*` THEN PostgreSQL cursor rowcount SHALL be required as optional single-row evidence, rowcount=0 with no returned row SHALL be the only valid no-representative-edge cleanup result, rowcount=1 with a returned row SHALL be the only valid representative fact refresh, missing/invalid/mismatched rowcount SHALL fail before derived item-scoped facts are cleared or affected-item accounting continues, and repository code SHALL not restore representative refresh success through chained `.fetchone()` or returned-row presence alone.
- AC409. WHEN `NewsRepository.claim_unprocessed_items(...)` leases raw/retryable `news_items` for `NewsItemProcessWorker` through `UPDATE news_items ... RETURNING items.*` claim rows THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned claim rows, rowcount=0 with no returned rows SHALL be the only no-work result, missing/invalid/mismatched rowcount SHALL fail before deterministic item processing, retry/terminal transitions, or dirty enqueue treat those rows as leased work, and repository code SHALL not restore claim success through chained `.fetchall()` or returned-list length alone.
- AC410. WHEN `NewsRepository.clear_current_briefs_outside_schema(...)` deletes stale current `news_item_agent_briefs` rows through `DELETE ... RETURNING news_item_id` schema cleanup THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned deleted ids, rowcount=0 with no returned rows SHALL be the only no-work cleanup result, missing/invalid/mismatched rowcount SHALL fail before stale-brief cleanup accounting is reported, and repository code SHALL not restore cleanup success through chained `.fetchall()` or returned-list length alone.
- AC411. WHEN `NewsProjectionDirtyTargetRepository.claim_due(...)` claims due `news_projection_dirty_targets` through `UPDATE ... RETURNING news_projection_dirty_targets.*` claim rows THEN PostgreSQL cursor rowcount SHALL be required, rowcount SHALL match returned claim rows, rowcount=0 with no returned rows SHALL be the only no-work result, missing/invalid/mismatched rowcount SHALL fail before page/source-quality projection workers treat those rows as leased work, and repository code SHALL not restore claim success through chained `.fetchall()` or returned-list length alone.
- AC412. WHEN `NotificationRepository` aggregates an existing `notifications` fact through `UPDATE notifications` after an insert conflict THEN PostgreSQL cursor rowcount SHALL be required, rowcount=1 SHALL be the only valid aggregate update result, missing/invalid/zero/multi-row rowcount SHALL fail before `NotificationInsertOutcome.aggregated` or external delivery requeue state is reported, and repository code SHALL not restore aggregate success through bare `self.conn.execute(...)`, direct `return True`, or readback presence alone.
- AC413. WHEN token fact repositories write `token_evidence`, `token_intents`, `token_intent_evidence`, `token_intent_lookup_keys`, or `token_intent_resolutions` THEN PostgreSQL cursor rowcount SHALL be required before facts, links, lookup replacements, delete accounting, or current resolutions are trusted; required evidence/intent/resolution upserts SHALL use `RETURNING *` with rowcount=1 and a returned row, evidence-link `ON CONFLICT DO NOTHING` SHALL allow only rowcount 0/1, lookup replacement deletes SHALL require real non-negative rowcount while each lookup upsert SHALL require rowcount=1, resolution supersede UPDATE SHALL require rowcount=1, and repository code SHALL not restore success through fallback `SELECT`, returned-row presence, or rowcount-default compatibility.
- AC414. WHEN `PulseEvidenceRepository.upsert_packet(...)` links a sealed evidence packet to `pulse_agent_runs` after the packet `RETURNING` upsert succeeds THEN the run-link `UPDATE pulse_agent_runs` SHALL validate PostgreSQL cursor rowcount=1 before `upsert_packet(...)` returns; missing, invalid, zero-row, or multi-row run-link rowcount SHALL fail as `pulse_evidence_repository_rowcount_required` or `pulse_evidence_repository_rowcount_invalid`, and repository code SHALL not trust packet `RETURNING` evidence or bare UPDATE execution as proof of the run audit link.
- AC415. WHEN `ProjectionRepository.claim_dirty_ranges(...)` leases `projection_dirty_ranges` through `UPDATE ... RETURNING ranges.*` THEN PostgreSQL cursor rowcount SHALL be required and SHALL match returned claimed rows before dirty-range work is treated as leased; rowcount=0 with no returned rows SHALL be the only valid no-work claim result, missing/invalid/mismatched rowcount SHALL fail as `projection_repository_rowcount_required` or `projection_repository_rowcount_invalid`, and repository code SHALL not restore claim success through chained `.fetchall()` or returned-row length alone.
- AC416. WHEN `ProjectionRepository` advances offsets, starts runs, finishes runs, or enqueues dirty ranges through `projection_offsets`, `projection_runs`, or `projection_dirty_ranges` THEN ordinary control-plane writes SHALL validate PostgreSQL cursor rowcount exactly one before state is trusted; `start_run(...)` SHALL use `INSERT ... RETURNING *` and require both rowcount=1 and a returned row, missing/invalid/zero/multi-row rowcount SHALL fail as `projection_repository_rowcount_required` or `projection_repository_rowcount_invalid`, and repository code SHALL not restore start-run success through fallback `run_by_id(...)` readback or bare execute success.
- AC417. WHEN `/api/token-radar` composes Token Radar rows with `NarrativeReadModel` THEN the route SHALL pass the formal public row `target.target_type` / `target.target_id` object through unchanged, `NarrativeReadModel` SHALL extract that nested identity before narrative digest lookup, and API route code SHALL NOT synthesize temporary top-level `target_type` / `target_id`, `_synthetic_target_type`, `_synthetic_target_id`, `_with_top_level_targets`, or `_strip_synthetic_targets` compatibility fields/helpers for hydration.
- AC418. WHEN `RegistryRepository` writes `registry_assets`, `cex_tokens`, `price_feeds`, or `us_equity_symbols` through required upsert paths THEN PostgreSQL cursor rowcount SHALL be required as rowcount=1 with a returned row before registry facts/routes/symbols are returned; missing, invalid, zero, multi-row, or rowcount=1/no-row evidence SHALL fail as `registry_repository_rowcount_required` or `registry_repository_rowcount_invalid`, and repository code SHALL not restore success through fallback `_row_by_id`, `dict(row) if row else {}`, returned-row presence, or post-write readback.
- AC419. WHEN `PulseJobsRepository` mutates `pulse_agent_jobs` through single-row `RETURNING` paths THEN PostgreSQL cursor rowcount SHALL be required and SHALL match returned-row presence before job state, retry/dead classification, terminal retry, timeout cancellation, release, or terminal ledger effects are reported; required enqueue SHALL be rowcount=1 with a returned row, optional claim/success/failure/retry/cancel/release paths SHALL accept only rowcount=0 with no row or rowcount=1 with one row, and repository code SHALL not restore job state-machine success through chained `.fetchone()`, `_row(row)`, `_optional_row(row)`, or returned-row presence alone.
- AC420. WHEN `DiscoveryRepository` claims due lookup work or writes `token_discovery_results` running/found/error state THEN PostgreSQL cursor rowcount SHALL be required before discovery control/result state is trusted; due-claim rowcount SHALL match returned claim rows, rowcount=0 with no rows SHALL be the only no-work claim result, `start_lookup(...)` and `fail_lookup(...)` SHALL use `RETURNING *` with rowcount=1 and a returned row, `finish_lookup(...)` SHALL require rowcount=1 before changed state is reported, and repository code SHALL not restore result success through chained `.fetchall()`, returned-list length, bare execute success, or `self.result(...) or {}` readback.
- AC421. WHEN ops projection dirty repair builds News page, brief-input, or source-quality dirty targets THEN the repair read path SHALL be a minimal keyset scan: page/brief repair SHALL read only item id, source watermark, and persisted agent-admission status from `news_items`; source-quality-only repair SHALL not scan `news_items`; and repair SQL SHALL not reintroduce source joins, LATERAL token/fact aggregates, admission JSON, provider signal, or provider impact payloads.
- AC422. WHEN public WebSocket `/ws` handles a subscribe replay request THEN replay SHALL be a bounded read-side query: `replay` SHALL be capped by a named constant, total subscription filter values across handles, contract addresses, symbols, and market targets SHALL be capped before client state changes, oversized subscriptions SHALL return `too_many_filters`, and token-filter replay SHALL divide the total replay budget across selected symbols/addresses instead of running the full replay limit once per filter.
- AC423. WHEN public WebSocket `/ws` hydrates replay event payloads THEN replay SHALL batch projected event payload reads for the selected replay page through `entities_for_events`, `alerts_for_events`, `intents_for_events`, and `event_tokens.for_events`, SHALL preserve single-event hydration for live publish payloads only, and SHALL NOT run per-event projection lookups for each replay item.
- AC424. WHEN `/api/watchlist/handles/overview` reads configured handle metrics THEN `WatchlistIntelRepository.handles_overview(...)` SHALL batch the configured handle keyset in one SQL query using `input_handles` and `WITH ORDINALITY`, SHALL preserve configured input order, and SHALL NOT issue per-handle latest-event/count SQL through `_handle_overview_counts` or equivalent looped repository reads.
- AC425. WHEN `/api/watchlist/handles/overview` reads configured handle latest-event and recent-count metrics THEN latest-event lookup SHALL use an indexable lateral `ORDER BY events.received_at_ms DESC, events.event_id DESC LIMIT 1` probe per distinct configured handle, recent counts SHALL be constrained by `since_ms`, and repository SQL SHALL NOT use full-history `MAX(events.received_at_ms)` aggregation to compute latest events.
- AC426. WHEN `/api/notifications/account-quality` or CLI account-quality reads multiple handles THEN `AccountQualityService.account_quality_for_handles(...)` SHALL call a batched repository read once for the normalized handle keyset, `AccountQualityRepository.accounts_quality(...)` SHALL read profiles, token-call stats, and quality snapshots through fixed keyset SQL using `WITH ORDINALITY`, stats and snapshots SHALL enforce per-handle limits with PostgreSQL `ROW_NUMBER() OVER (PARTITION BY handle ...)`, and code SHALL NOT call the single-handle `account_quality(...)` reader once per handle.
- AC427. WHEN resolution refresh reprocesses a batch of recent token intents THEN token evidence hydration SHALL read the selected intent keyset through `TokenEvidenceRepository.evidence_for_intents(...)` using `unnest(%s::text[]) WITH ORDINALITY`, SHALL group returned evidence by `intent_id` before resolver calls, and SHALL NOT query `evidence_for_intent(...)` once per intent inside the reprocess loop.
- AC428. WHEN Search handles an OR-symbol query such as `btc OR eth` THEN target resolution SHALL call `SearchEventsQuery.resolve_symbols(...)` once for the normalized symbol keyset, the repository SQL SHALL use `unnest(%s::text[]) WITH ORDINALITY` plus `distinct_symbols` to preserve input order and de-dupe symbols inside PostgreSQL, asset ambiguity SHALL be computed with `COUNT(*) OVER (PARTITION BY distinct_symbols.symbol)`, and service code SHALL NOT loop over `or_symbols` to call the single-symbol `resolve_targets(...)` reader once per token.
- AC429. WHEN `NarrativeReadModel.hydrate_target_posts(...)` hydrates selected post semantics THEN `NarrativeRepository.semantics_for_posts(...)` SHALL read the selected `(event_id, target_type, target_id)` post keyset through one SQL statement using `unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY`, SHALL de-dupe through `distinct_posts`, SHALL use a lateral latest-row probe over `token_mention_semantics`, and SHALL NOT loop over posts to call `SELECT ... FROM token_mention_semantics ... LIMIT 1` once per post.
- AC430. WHEN `NotificationRuleEngine` evaluates Signal Pulse notification candidates THEN candidate discovery SHALL call `PulseReadRepository.list_signal_pulse_notification_candidates(...)` once with the configured window, scopes, statuses, and per-scope/status budget, the repository SQL SHALL materialize scopes/statuses through `unnest(... WITH ORDINALITY)` keysets and use `ROW_NUMBER() OVER (PARTITION BY scope,status ...)` to bound each bucket, and rule service code SHALL NOT loop over `PulseReadRepository.list_candidates(...)` cursor pages for every scope/status combination.
- AC431. WHEN `NotificationRuleEngine` evaluates watched-account activity THEN the configured `watched_activity_window_ms` SHALL be converted to `since_ms` and passed into `EvidenceRepository.recent_events(...)`, `EvidenceRepository.recent_events(...)` SHALL push that predicate into PostgreSQL as `e.received_at_ms >= %s`, and the notification rule SHALL NOT rely only on service-layer filtering after reading a generic recent watched-event page.
- AC432. WHEN account-alert rows are read through `AccountAlertService.account_alerts(...)` for API, CLI, or notification rule evaluation THEN callers SHALL pass `now_ms` explicitly, `AccountAlertService` SHALL pass that value through to `SignalRepository.account_alerts(...)`, and `NotificationRuleEngine._watched_account_token_alerts(...)` SHALL use the worker evaluation clock instead of allowing the repository to compute the alert window from wall-clock time.
- AC433. WHEN public WebSocket `/ws` replays events for subscribed `cas` or `symbols` token filters THEN `_replay_events(...)` SHALL call `EvidenceRepository.recent_events_for_token_filters(...)` once with the total replay limit, the computed per-filter bucket limit, and the normalized CA/symbol keysets; the repository SQL SHALL materialize filters through `unnest(%s::text[], %s::text[], %s::text[]) WITH ORDINALITY`, de-dupe filters, and use `ROW_NUMBER() OVER (PARTITION BY filter_kind, filter_chain, filter_value ...)` to bound each token-filter bucket inside PostgreSQL; and WebSocket replay code SHALL NOT loop over `client.cas` or `client.symbols` to call `recent_events(...)` once per filter.
- AC434. WHEN `pulse_policy_evaluator.fetch_radar_rows(...)` reads evaluated Token Radar current rows THEN it SHALL query `token_radar_current_rows` once for the evaluated window/scope keysets, the SQL SHALL use `token_radar_current_rows."window" = ANY(%s)` and `token_radar_current_rows.scope = ANY(%s)` while preserving ready publication-state gating, and the evaluator SHALL NOT loop over `EVALUATED_WINDOWS` and `EVALUATED_SCOPES` to issue one radar-current SQL per combination.
- AC435. WHEN `ProjectionValidationAudit.run(...)` validates sampled Token Radar current-row references THEN it SHALL compute checked and missing intent/asset counts through one sampled aggregate SQL using `sampled_radar_rows`, `LEFT JOIN token_intents`, `LEFT JOIN registry_assets`, and `COUNT(*) FILTER`; it SHALL NOT loop over sampled rows to issue one `token_intents` or `registry_assets` `SELECT` per row.
- AC436. WHEN `NewsItemProcessWorker` enqueues page or item-brief dirty targets for processed news items THEN `source_watermark_ms` SHALL come only from positive persisted `news_items.fetched_at_ms` or `news_items.published_at_ms`, missing source time SHALL fail closed with `news_item_process_source_watermark_required`, and the worker SHALL NOT use runtime `now_ms`, `fallback_ms`, or processing time as a source-watermark fallback.
- AC437. WHEN `build_news_page_row(...)` publishes `news_page_rows.latest_at_ms` THEN it SHALL use only positive canonical item `published_at_ms`, missing or invalid published time SHALL fail closed with `news_page_projection_published_at_required`, and page projection SHALL NOT use `computed_at_ms`, `fetched_at_ms`, or worker processing time as a `latest_at_ms` fallback.
- AC438. WHEN `TokenImageMirrorWorker` handles failed `token_image_source_dirty_targets` THEN dirty-source retry budget SHALL come from formal `settings.workers.token_image_mirror.max_attempts`, retryable claims SHALL reschedule in `token_image_source_dirty_targets`, exhausted claims SHALL be deleted and terminalized in `worker_queue_terminal_events` with target key `source_url_hash:target_type:target_id`, and Token Profile image admission SHALL NOT re-enqueue unresolved terminal events before operator action.
- AC439. WHEN Binance CEX profile sync writes `cex_token_profiles` source-cache rows THEN provider output SHALL be materialized as formal mapping records with required `base_symbol`, `provider`, `symbol`, `logo_url`, `source_ref`, and mapping-shaped `raw_payload` before opening the DB transaction; object-attribute profile compatibility, provider/symbol fallbacks, and empty raw-payload defaults SHALL fail before source-cache SQL.
- AC440. WHEN Token Profile Current projection builds or repository writes `token_profile_current` rows THEN projection output and repository input SHALL use formal `quality_flags_json` and `source_payload_json` fields, missing or incorrectly shaped JSON fields SHALL fail before serving-row SQL, and repository code SHALL NOT restore old `quality_flags` / `source_payload` aliases or empty JSON defaults.
- AC441. WHEN Token Radar projection enqueues downstream Pulse Trigger, Narrative Admission, or Token Profile Current dirty targets from current rows THEN `source_watermark_ms` SHALL come only from positive current-row `source_max_received_at_ms`, missing or invalid source watermarks SHALL fail closed with `token_radar_downstream_source_watermark_required`, and projection code SHALL NOT use `computed_at_ms` or projection runtime time as a downstream source-watermark fallback.
- AC442. WHEN Token Profile Current dirty targets are enqueued by Token Radar, Asset Profile Refresh, Token Image Mirror, or ops image repair THEN producer rows SHALL carry a positive integer `source_watermark_ms`, `TokenProfileCurrentDirtyTargetRepository` SHALL reject missing, tuple-shaped, zero, negative, boolean, string, or otherwise invalid source watermarks with `token_profile_current_dirty_target_source_watermark_required`, and producer/repository/ops code SHALL NOT use `computed_at_ms`, `updated_at_ms`, tuple target identity, or runtime `now_ms` as a source-watermark fallback.
- AC443. WHEN Token Profile Current admits image-source dirty targets for Token Image Mirror THEN source candidates SHALL carry a positive integer source-row `observed_at_ms` as `source_watermark_ms`, `TokenImageSourceDirtyTargetRepository` SHALL reject missing, zero, negative, boolean, string, target-level `observed_at_ms` fallback, or otherwise invalid source watermarks with `token_image_source_dirty_target_source_watermark_required`, Token Image Source admission SHALL fail missing or invalid source freshness with `token_image_source_admission_source_watermark_required`, and producer/repository code SHALL NOT use `updated_at_ms`, target-level `observed_at_ms`, or runtime `now_ms` as an image-source source-watermark fallback.
- AC444. WHEN Asset Profile Refresh targets are enqueued THEN producer rows SHALL carry a positive integer `source_watermark_ms`, `AssetProfileRefreshTargetRepository` SHALL reject missing, zero, negative, boolean, string, `updated_at_ms` fallback, or otherwise invalid source watermarks with `asset_profile_refresh_target_source_watermark_required`, and producer/repository code SHALL NOT use source-cache `updated_at_ms` or runtime `now_ms` as an Asset Profile Refresh source-watermark fallback.
- AC445. WHEN Token Radar projection or ops repair enqueues Token Capture Tier dirty rank-set work THEN producer rows SHALL derive `source_watermark_ms` only from positive current-row `source_max_received_at_ms`, `TokenCaptureTierDirtyTargetRepository` SHALL require an explicit positive integer `source_watermark_ms` and reject missing, zero, negative, boolean, string, row-level fallback, or otherwise invalid source watermarks with `token_capture_tier_dirty_target_source_watermark_required`, ops repair SHALL fail malformed current-row watermarks with `ops_capture_tier_rank_set_source_watermark_required`, and producer/repository/ops code SHALL NOT use `computed_at_ms`, row-level legacy `source_watermark_ms`, `0`, or runtime `now_ms` as a Token Capture Tier source-watermark fallback.
- AC446. WHEN Token Radar projection enqueues Pulse Trigger or Narrative Admission dirty targets THEN producer rows SHALL carry a positive integer `source_watermark_ms`, `PulseTriggerDirtyTargetRepository` and `NarrativeAdmissionDirtyTargetRepository` SHALL reject missing, zero, negative, boolean, string, or otherwise invalid source watermarks with `pulse_trigger_dirty_target_source_watermark_required` / `narrative_admission_dirty_target_source_watermark_required`, and producer/repository code SHALL NOT use `computed_at_ms`, runtime `now_ms`, `0`, or zero-watermark enqueue compatibility branches as source-watermark fallbacks.
- AC447. WHEN News page, item-brief, or source-quality window dirty targets are enqueued THEN producer rows SHALL carry a positive integer `source_watermark_ms`, `NewsProjectionDirtyTargetRepository` and `news_projection_work` SHALL reject missing, zero, negative, boolean, string, or otherwise invalid producer watermarks with `news_projection_dirty_target_source_watermark_required`, source-quality `_refresh` SHALL remain a source-scoped expansion control target only, source-quality window targets SHALL derive `source_watermark_ms` from positive `latest_item_published_at_ms` rather than `computed_at_ms` or runtime `now_ms`, ops projection-dirty repair SHALL reject malformed News item source watermarks with `ops_news_projection_dirty_source_watermark_required`, and producer/repository/ops SQL SHALL NOT retain zero-watermark enqueue compatibility branches such as `source_watermark_ms = 0`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Stocks UI expected ready quote snapshots. | Medium | Keep quote block shape stable but report explicit unavailable status and update docs/tests. |
| Removing the resolution helper breaks tests that were bypassing runtime sessions. | Medium | Move tests to `ResolutionRefreshWorker` or pure provider fetch/persist helpers before deleting the helper. |
| Notification cleanup migration cannot run inside a transaction if using `CREATE INDEX CONCURRENTLY`. | High | Use the repository's existing concurrent-index migration style and schema tests. |
| Pulse handle semantics narrow unexpectedly. | Medium | Prefer an existing compact edge when available; otherwise update API/docs/frontend tests to make narrowed semantics explicit. |

## Evolution path

A future feature can introduce a persisted US equity quote read model with one writer, stable instrument keys, source freshness metadata, and explicit backfill/retention. This feature must not foreclose that lane, but it also must not fake that lane with request-time provider IO.

## Alternatives considered

- Keep request-time Yahoo quote provider with caching - rejected because it preserves an external IO dependency in a CQRS read API and keeps the root boundary violation.
- Add a new stock quote worker now - rejected because the current goal is root governance and compatibility deletion, and a durable equity market lane needs its own spec, provider contract, and retention model.
- Keep `run_resolution_refresh_once` as a shim - rejected because it creates a second execution path with different session/provider boundaries.
- Add JSONB expression indexes for Pulse event id expansion - rejected because it optimizes a compatibility shape rather than restoring an indexable read model.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Remove provider IO from `/api/stocks-radar`, align manifest/runtime contracts, bound maintenance SQL, and record SDD evidence. |
| Ask first | Introduce a new persisted stock quote lane or materially change public Pulse handle semantics beyond the minimum needed to remove JSONB expansion. |
| Never | Keep compatibility shims, hidden request-time provider fallbacks, or unbounded maintenance work in serving hot paths. |
