# Tasks — Backend KISS whole-chain simplification

**Status**: Review
**Owning plan**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/plan.md`
**Worktree**: `.worktrees/backend-kiss-deep-audit/`
**Branch**: `codex/backend-kiss-deep-audit`
**Approved by**: delegated `/goal` for whole-architecture KISS review and implementation
**Approved at**: 2026-07-22

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records autonomous scope, protected invariants, and conflict boundaries. |
| Checklist | `spec.md` defines auditable quality gates for review, cuts, tests, and coordination. |
| Analyze | Four validated read-only audits and parent call-graph checks narrow exact keep/cut/defer decisions in `plan.md`. |
| Implement | Tasks 6–9 own disjoint hard-cut slices; Task 10 owns final integration, documentation, and verification. |
| Verify | `verification.md` is present and remains honest about unrun gates. |

## Tasks

### Task 1 — Audit runtime, composition, configuration, operations, and surfaces `[P]`

- **File(s)**: `src/parallax/app/runtime`, `src/parallax/app/operations`, `src/parallax/app/surfaces`, `src/parallax/platform/config`, `src/parallax/platform/runtime`, `src/parallax/platform/agent_execution.py`
- **Owner**: runtime-scout subagent; parent records and validates the returned report
- **Depends on**: none
- **Touch set**: `src/parallax/app/runtime`, `src/parallax/app/operations`, `src/parallax/app/surfaces`, `src/parallax/platform/config`, `src/parallax/platform/runtime`, `src/parallax/platform/agent_execution.py`
- **Conflict set**: `.agents/skills/**`; `web/**`; `docs/sdd/features/active/2026-07-22-docker-build-contract-fix`; `docs/sdd/features/active/2026-07-22-news-fetch-retention-index`
- **Failing test first**: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q` — use the green root invariant suite as the read-only audit baseline; no implementation test is added in this task.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-1.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-1.md`
- **Review result**: accepted
- **Implementation**: Trace bootstrap, provider wiring, worker factories/manifest/scheduler/kernel, settings, ops, CLI, HTTP/WS boundaries; identify only current, evidenced redundancy or indirection.
- **Verification**: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py`
- **Review owner**: parent agent
- **Factory lane**: Risk radar
- **Deterministic constraints**: canonical architecture/reliability/worker docs; no secrets; separate inactive semantics for disabled, intentionally-not-started, and unavailable.
- **On-demand context**: `AGENTS.md`; task-reading matrix; `docs/ARCHITECTURE.md`; `docs/WORKERS.md`; `docs/WORKER_FLOW.md`; `docs/RELIABILITY.md`; existing implementation audit.
- **Kill/defer criteria**: stop any proposal that adds a framework, compatibility path, runtime truth copy, or edits files.
- **Eval/repair signal**: evidence-backed finding count; false-positive count after parent review.
- **Status**: [x]

### Task 2 — Audit fact, identity, market, Radar, evidence, and notification flows `[P]`

- **File(s)**: `src/parallax/domains/evidence`, `src/parallax/domains/ingestion`, `src/parallax/domains/asset_market`, `src/parallax/domains/token_intel`, `src/parallax/domains/notifications`
- **Owner**: domain-scout subagent; parent records and validates the returned report
- **Depends on**: none
- **Touch set**: `src/parallax/domains/evidence`, `src/parallax/domains/ingestion`, `src/parallax/domains/asset_market`, `src/parallax/domains/token_intel`, `src/parallax/domains/notifications`
- **Conflict set**: `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0186_runtime_projection_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`; `.agents/skills/**`; `web/**`
- **Failing test first**: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q` — use the green root invariant suite as the read-only audit baseline and map each proposed cut to positive coverage.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-2.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-2.md`
- **Review result**: accepted
- **Implementation**: Trace raw input through evidence/identity/market facts, dirty targets, Token Radar/current profiles, notifications, public consumers, and recovery; distinguish essential domain complexity from duplicated state machines/helpers/tests.
- **Verification**: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py`
- **Review owner**: parent agent
- **Factory lane**: Risk radar
- **Deterministic constraints**: single truth, stable key, single writer, unchanged zero-write, bounded catch-up, transaction/I/O separation, terminal evidence retention.
- **On-demand context**: required root docs; read-model checklist; Evidence, Asset Market, Token Intel, and Notifications architecture maps and current code/tests.
- **Kill/defer criteria**: stop proposals that remove material facts, rebuildability, side-effect ledgers, or the raw-event safety hold.
- **Eval/repair signal**: evidence-backed finding count; rejected LOC-only suggestions.
- **Status**: [x]

### Task 3 — Audit News, Macro, repository/test architecture, and directory complexity `[P]`

- **File(s)**: `src/parallax/domains/news_intel`, `src/parallax/domains/macro_intel`, `tests/unit/domains/news_intel`, `tests/unit/domains/macro_intel`
- **Owner**: test-domain-scout subagent; parent records and validates the returned report
- **Depends on**: none
- **Touch set**: `src/parallax/domains/news_intel`, `src/parallax/domains/macro_intel`, `tests/unit/domains/news_intel`, `tests/unit/domains/macro_intel`
- **Conflict set**: `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`; `tests/unit/test_postgres_schema.py`; `tests/integration/test_postgres_schema_runtime.py`; `.agents/skills/**`; `web/**`
- **Failing test first**: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q` — use the green root invariant suite as the read-only audit baseline; every test-removal suggestion must name equivalent behavior evidence.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-3.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-3.md`
- **Review result**: accepted
- **Implementation**: Trace News and Macro facts/projections/model ledgers, inspect oversized repositories/services/tests, identify fake-PostgreSQL/source-shape/retired-contract duplication and directory indirection with concrete keep/cut evidence.
- **Verification**: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py`
- **Review owner**: parent agent
- **Factory lane**: Risk radar
- **Deterministic constraints**: do not edit the active News FK index scope; preserve model audit, terminal evidence, Macro fact truth, stable projections, and exact public contracts.
- **On-demand context**: required root docs; News/Macro architecture maps; current repository/service/test code; existing implementation audit.
- **Kill/defer criteria**: stop test-deletion suggestions without equivalent executable behavior evidence or changes that only split files without reducing decision paths.
- **Eval/repair signal**: redundant-test LOC identified versus coverage retained; parent-rejected findings.
- **Status**: [x]

### Task 4 — Audit provider adapters and the PostgreSQL execution plane `[P]`

- **File(s)**: `src/parallax/integrations`; `src/parallax/platform/db/queue_terminal.py`; `src/parallax/platform/db/postgres_audit.py`; `src/parallax/platform/db/postgres_client.py`; `src/parallax/platform/db/postgres_migrations.py`; `src/parallax/platform/db/write_contract.py`; `src/parallax/platform/db/json_safety.py`; `src/parallax/platform/db/alembic/env.py`
- **Owner**: adapter-db-scout subagent; parent records and validates the returned report
- **Depends on**: none
- **Touch set**: `src/parallax/integrations`; `src/parallax/platform/db/queue_terminal.py`; `src/parallax/platform/db/postgres_audit.py`; `src/parallax/platform/db/postgres_client.py`; `src/parallax/platform/db/postgres_migrations.py`; `src/parallax/platform/db/write_contract.py`; `src/parallax/platform/db/json_safety.py`; `src/parallax/platform/db/alembic/env.py`
- **Conflict set**: `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0186_runtime_projection_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`; `.agents/skills/**`; `web/**`
- **Failing test first**: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q` — use the green root invariant suite as the audit baseline; do not infer provider or physical-PostgreSQL behavior from unit doubles.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-4.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-4.md`
- **Review result**: accepted
- **Implementation**: Trace provider protocol-to-adapter ownership, timeout/close/error semantics, PostgreSQL pool/write/terminal-evidence primitives, and current callers; identify only unused compatibility branches, duplicate state, or generic machinery without a current consumer.
- **Verification**: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py`
- **Review owner**: parent agent
- **Factory lane**: Risk radar
- **Deterministic constraints**: preserve explicit provider unavailability, external-I/O boundaries, immutable migrations, transaction ownership, terminal evidence, and bounded queue operations.
- **On-demand context**: `AGENTS.md`; `docs/agent-playbook/task-reading-matrix.md`; `docs/ARCHITECTURE.md`; `docs/CONTRACTS.md`; `docs/SECURITY.md`; `docs/RELIABILITY.md`; `docs/references/POSTGRES_PERFORMANCE.md`; existing implementation audit.
- **Kill/defer criteria**: stop proposals requiring secrets, live-provider inference, physical query-performance claims, migration rewrites, or a new generic adapter/repository framework.
- **Eval/repair signal**: accepted current-consumer cuts versus rejected adapter-size or provider-policy false positives.
- **Status**: [x]

### Task 5 — Cross-validate findings and authorize exact hard-cut tasks

- **File(s)**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/spec.md`, `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/plan.md`, `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/tasks.md`
- **Owner**: parent
- **Depends on**: Task 1-4
- **Touch set**: `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit`
- **Conflict set**: `src/parallax/**`; `tests/**`; `web/**`; `.agents/skills/**`
- **Failing test first**: `uv run pytest tests/architecture/test_kiss_runtime_invariants.py -q` — every accepted finding must map to this durable contract or a new/existing positive behavior test before implementation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Reopened cited source and current call sites. Accepted direct duplicate/dead/fake-generalization cuts; rejected blanket C90/large-file splitting and the terminal-reason deletion; deferred changes needing live provider/PostgreSQL evidence or a new durable state machine. Revised `plan.md` and added Tasks 6–10 before production edits.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py`
- **Review owner**: parent agent
- **Factory lane**: Spec/plan
- **Deterministic constraints**: approved spec, active touch-set coordination, no compatibility glue, no undocumented contract or schema change.
- **On-demand context**: validated reports, source/diff, current tests, domain architecture maps.
- **Kill/defer criteria**: defer any finding needing live PostgreSQL/provider evidence or overlapping an active feature.
- **Eval/repair signal**: accepted/rejected/deferred finding counts and reasons.
- **Status**: [x]

### Task 6 — Simplify worker kernel and concrete worker settings `[P]`

- **File(s)**: `src/parallax/platform/runtime/worker_base.py`; `src/parallax/platform/config/settings.py`; `tests/unit/test_worker_base_runtime.py`; `tests/unit/test_run_worker_once.py`; `tests/unit/test_worker_settings.py`; `tests/unit/test_settings.py`
- **Owner**: worker-config implementation subagent; parent reviews and repairs
- **Depends on**: Task 5
- **Touch set**: `src/parallax/platform/runtime/worker_base.py`; `src/parallax/platform/config/settings.py`; `tests/unit/test_worker_base_runtime.py`; `tests/unit/test_run_worker_once.py`; `tests/unit/test_worker_settings.py`; `tests/unit/test_settings.py`
- **Conflict set**: `src/parallax/domains`; `src/parallax/integrations`; `src/parallax/app`; `docs/**`; `.agents/skills`; `web/**`
- **Failing test first**: `uv run pytest -q tests/unit/test_worker_base_runtime.py tests/unit/test_worker_settings.py` — preserve sequential iteration, re-entry, failure recovery, disabled, manifest alignment, and extra-forbid behavior.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-6.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-6.md`
- **Review result**: accepted
- **Implementation**: create one private iteration path and one lifecycle flag; localize worker-only settings fields to actual consumers; remove unused `BackoffPolicy.kind` and `write_default_workers_config()` without aliases.
- **Verification**: `uv run pytest -q tests/unit/test_worker_base_runtime.py tests/unit/test_run_worker_once.py tests/unit/test_worker_settings.py tests/unit/test_settings.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: preserve interval/backoff/start-stop semantics and current operator-config load; do not weaken extra-forbid.
- **On-demand context**: worker docs, runtime audit report, exact settings consumers.
- **Kill/defer criteria**: stop if a removed setting has a current consumer or operator config key.
- **Eval/repair signal**: one iteration body; current config loads; targeted behavior passes.
- **Status**: [x]

### Task 7 — Simplify ingest, resolution, Radar, and News projection flow `[P]`

- **File(s)**: `src/parallax/domains/ingestion/providers.py`; `src/parallax/domains/ingestion/runtime/collector_service.py`; `src/parallax/app/runtime/bootstrap.py`; `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`; `src/parallax/domains/token_intel/interfaces.py`; `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`; `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`; `src/parallax/domains/token_intel/services/token_resolution_refresh.py`; `src/parallax/domains/news_intel/runtime/news_projection_work.py`; `tests/unit/test_collector_service.py`; `tests/contract/test_provider_protocol_fixtures.py`; `tests/unit/test_token_intent_rebuild_runtime.py`; `tests/integration/test_token_intent_rebuild.py`; `tests/unit/test_token_radar_projection_worker.py`; `tests/unit/domains/news_intel/test_news_projection_work.py`
- **Owner**: domain-flow implementation subagent; parent reviews and repairs
- **Depends on**: Task 5
- **Touch set**: `src/parallax/domains/ingestion/providers.py`; `src/parallax/domains/ingestion/runtime/collector_service.py`; `src/parallax/app/runtime/bootstrap.py`; `src/parallax/domains/asset_market/runtime/resolution_refresh_worker.py`; `src/parallax/domains/token_intel/interfaces.py`; `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`; `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py`; `src/parallax/domains/token_intel/services/token_resolution_refresh.py`; `src/parallax/domains/news_intel/runtime/news_projection_work.py`; `tests/unit/test_collector_service.py`; `tests/contract/test_provider_protocol_fixtures.py`; `tests/unit/test_token_intent_rebuild_runtime.py`; `tests/integration/test_token_intent_rebuild.py`; `tests/unit/test_token_radar_projection_worker.py`; `tests/unit/domains/news_intel/test_news_projection_work.py`
- **Conflict set**: `src/parallax/platform/runtime`; `src/parallax/platform/config`; `src/parallax/integrations`; `src/parallax/platform/db`; `web/**`; `.agents/skills`
- **Failing test first**: `uv run pytest -q tests/unit/test_collector_service.py tests/unit/test_token_intent_rebuild_runtime.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py` — preserve publication, rebuild, Radar scheduling, and News projection behavior.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-7.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-7.md`
- **Review result**: accepted
- **Implementation**: publish ingest-returned resolutions, delete the redundant repository protocol/bootstrap query, remove placeholder projection/anchor fields and unused rebuild argument, delete the duplicate Radar missing-work pass, and call `servable_news_item_ids` directly.
- **Verification**: `uv run pytest -q tests/unit/test_collector_service.py tests/contract/test_provider_protocol_fixtures.py tests/unit/test_token_intent_rebuild_runtime.py tests/integration/test_token_intent_rebuild.py tests/unit/test_token_radar_projection_worker.py tests/unit/domains/news_intel/test_news_projection_work.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: preserve material fact ownership, post-commit publication, stable Radar current identity, and bounded recovery.
- **On-demand context**: domain audit report and architecture maps.
- **Kill/defer criteria**: stop any change that removes a fact, dirty target, current writer, or recovery evidence.
- **Eval/repair signal**: zero redundant resolution read; no placeholder projection API; equivalent observable behavior.
- **Status**: [x]

### Task 8 — Hard-cut unused provider and PostgreSQL private surfaces `[P]`

- **File(s)**: `src/parallax/domains/asset_market/providers.py`; `src/parallax/app/runtime/provider_wiring/binance.py`; `src/parallax/app/runtime/provider_wiring/gmgn.py`; `src/parallax/app/runtime/provider_wiring/asset_market.py`; `src/parallax/app/runtime/provider_wiring/types.py`; `src/parallax/integrations/binance`; `src/parallax/integrations/gmgn`; `src/parallax/integrations/okx`; `src/parallax/integrations/news_feeds`; `src/parallax/platform/db/queue_terminal.py`; `src/parallax/platform/db/postgres_audit.py`; `src/parallax/app/surfaces/cli/commands/db.py`; `src/parallax/app/surfaces/cli/commands/queue_ops.py`; `tests/unit/test_provider_capabilities.py`; `tests/unit/test_providers_wiring.py`; `tests/unit/test_binance_usdm_futures_client.py`; `tests/unit/test_gmgn_openapi_client.py`; `tests/unit/test_okx_clients.py`; `tests/unit/integrations/news_feeds`; `tests/unit/test_queue_terminal.py`; `tests/integration/test_postgres_audit.py`
- **Owner**: provider-DB implementation subagent; parent reviews and repairs
- **Depends on**: Task 5
- **Touch set**: `src/parallax/domains/asset_market/providers.py`; `src/parallax/app/runtime/provider_wiring/binance.py`; `src/parallax/app/runtime/provider_wiring/gmgn.py`; `src/parallax/app/runtime/provider_wiring/asset_market.py`; `src/parallax/app/runtime/provider_wiring/types.py`; `src/parallax/integrations/binance`; `src/parallax/integrations/gmgn`; `src/parallax/integrations/okx`; `src/parallax/integrations/news_feeds`; `src/parallax/platform/db/queue_terminal.py`; `src/parallax/platform/db/postgres_audit.py`; `src/parallax/app/surfaces/cli/commands/db.py`; `src/parallax/app/surfaces/cli/commands/queue_ops.py`; `tests/unit/test_provider_capabilities.py`; `tests/unit/test_providers_wiring.py`; `tests/unit/test_binance_usdm_futures_client.py`; `tests/unit/test_gmgn_openapi_client.py`; `tests/unit/test_okx_clients.py`; `tests/unit/integrations/news_feeds`; `tests/unit/test_queue_terminal.py`; `tests/integration/test_postgres_audit.py`
- **Conflict set**: `src/parallax/platform/runtime`; `src/parallax/platform/config`; `src/parallax/domains/ingestion`; `src/parallax/domains/token_intel`; `web/**`; `.agents/skills`; `src/parallax/platform/db/alembic/versions`
- **Failing test first**: `uv run pytest -q tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/integrations/news_feeds/test_opennews_client.py tests/unit/test_queue_terminal.py` — preserve current provider, typed-policy, and terminal behavior.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-8.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-8.md`
- **Review result**: accepted
- **Implementation**: atomically remove Candle protocol/capability/wiring/adapters, three dead Binance endpoints, OpenNews URL policy fallback, duplicate CryptoPanic wrapper, unused feed/registry methods, terminal fake-active status, and unused audit binding.
- **Verification**: `uv run pytest -q tests/unit/test_provider_capabilities.py tests/unit/test_providers_wiring.py tests/unit/test_binance_usdm_futures_client.py tests/unit/test_okx_clients.py tests/unit/integrations/news_feeds tests/unit/test_queue_terminal.py tests/integration/test_postgres_audit.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: retain external payload aliases, retries, unavailable semantics, terminal ledger/classifier, PostgreSQL primitives, and immutable migrations.
- **On-demand context**: provider/DB audit report and current consumer searches.
- **Kill/defer criteria**: stop if any deleted surface has a current worker/service/public consumer.
- **Eval/repair signal**: no Candle/provider dead-end remains; current production adapters pass.
- **Status**: [x]

### Task 9 — Consolidate operations, canonicalization, and redundant tests

- **File(s)**: `src/parallax/app/runtime/repository_session.py`; `src/parallax/app/operations`; `src/parallax/app/runtime/provider_wiring`; `src/parallax/app/surfaces/api/routes_ops.py`; `src/parallax/app/surfaces/cli/commands/ops.py`; `src/parallax/app/surfaces/cli/parser.py`; `src/parallax/domains/asset_market/services/market_tick_persistence.py`; `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`; `src/parallax/domains/notifications/services/notification_rules.py`; `src/parallax/domains/news_intel/runtime`; `src/parallax/domains/evidence/repositories/evidence_repository.py`; `src/parallax/domains/token_intel/services/token_radar_projector.py`; `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`; `Makefile`; `tests/unit/test_api_async_boundaries.py`; `tests/unit/test_cli.py`; `tests/unit/test_ops_backfill_commands.py`; `tests/integration/test_cli.py`; `tests/unit/test_cli_search_query.py`; `tests/unit/test_worker_settings.py`; `tests/unit/test_settings.py`; `tests/unit/test_ops_diagnostics.py`; `tests/unit/test_api_ops_contract.py`; `tests/unit/test_ops_projection_dirty_targets.py`; `tests/unit/test_queue_health.py`; `tests/unit/test_providers_wiring.py`; `tests/unit/test_resolution_refresh_worker.py`; `tests/integration/test_resolution_refresh_worker.py`; `tests/integration/test_api_health.py`; `tests/support/fake_providers.py`; `tests/unit/domains/asset_market/test_chain_identity.py`; `tests/integration/domains/news_intel/test_news_page_repository.py`; `tests/unit/domains/news_intel/test_news_provider_contract.py`; `tests/unit/domains/news_intel/test_news_workers.py`; `tests/unit/domains/macro_intel/test_macro_migration_contract.py`; `tests/unit/domains/macro_intel/test_macro_sync_service.py`; `tests/unit/domains/macro_intel/test_macro_generation_swap.py`; `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`; `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`; `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`; `docs/generated/cli-help.md`
- **Removed file(s)**: `src/parallax/app/runtime/ops_diagnostics.py`; `src/parallax/app/runtime/ops_cli_queries.py`; `src/parallax/app/runtime/projection_dirty_targets.py`; `src/parallax/app/runtime/job_queue.py`; `tests/unit/test_cli_ops_contract.py`; `tests/unit/domains/news_intel/test_news_repository_filters.py`
- **Owner**: parent
- **Depends on**: Task 6-8
- **Touch set**: `src/parallax/app/runtime/repository_session.py`; `src/parallax/app/operations`; `src/parallax/app/runtime/provider_wiring`; `src/parallax/app/surfaces/api/routes_ops.py`; `src/parallax/app/surfaces/cli/commands/ops.py`; `src/parallax/app/surfaces/cli/parser.py`; `src/parallax/domains/asset_market/services/market_tick_persistence.py`; `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`; `src/parallax/domains/notifications/services/notification_rules.py`; `src/parallax/domains/news_intel/runtime`; `src/parallax/domains/evidence/repositories/evidence_repository.py`; `src/parallax/domains/token_intel/services/token_radar_projector.py`; `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`; `Makefile`; `tests/unit/test_api_async_boundaries.py`; `tests/unit/test_cli.py`; `tests/unit/test_ops_backfill_commands.py`; `tests/integration/test_cli.py`; `tests/unit/test_cli_search_query.py`; `tests/unit/test_worker_settings.py`; `tests/unit/test_settings.py`; `tests/unit/test_ops_diagnostics.py`; `tests/unit/test_api_ops_contract.py`; `tests/unit/test_ops_projection_dirty_targets.py`; `tests/unit/test_queue_health.py`; `tests/unit/test_providers_wiring.py`; `tests/unit/test_resolution_refresh_worker.py`; `tests/integration/test_resolution_refresh_worker.py`; `tests/integration/test_api_health.py`; `tests/support/fake_providers.py`; `tests/unit/domains/asset_market/test_chain_identity.py`; `tests/integration/domains/news_intel/test_news_page_repository.py`; `tests/unit/domains/news_intel/test_news_provider_contract.py`; `tests/unit/domains/news_intel/test_news_workers.py`; `tests/unit/domains/macro_intel/test_macro_migration_contract.py`; `tests/unit/domains/macro_intel/test_macro_sync_service.py`; `tests/unit/domains/macro_intel/test_macro_generation_swap.py`; `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`; `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`; `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`; `docs/generated/cli-help.md`
- **Conflict set**: `web/**`; `.agents/skills`; `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0186_runtime_projection_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`; `tests/unit/test_postgres_schema.py`; `tests/integration/test_postgres_schema_runtime.py`; coordinate with 2026-07-23-verification-harness-hard-cut for Makefile and coverage-only pragma cleanup
- **Failing test first**: `uv run pytest -q tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_providers_wiring.py tests/unit/domains/asset_market/test_chain_identity.py` — preserve exact ops and canonicalization behavior.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: move operations out of runtime with no re-exports, remove fake News domain branching, consolidate notification queue health, canonicalize chain/address through the domain helper, delete internal malformed bundle defense/dead runtime entries/stale Make target, remove only cross-validated test graveyard/private-shape assertions, and close strict typing at existing `Any` boundaries without runtime adapters or compatibility paths.
- **Verification**: `uv run pytest -q tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py tests/unit/test_ops_projection_dirty_targets.py tests/unit/test_queue_health.py tests/unit/test_providers_wiring.py tests/unit/domains/asset_market/test_chain_identity.py tests/architecture/test_kiss_runtime_invariants.py`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: exact public payloads, one queue-health calculation, no compatibility modules, no secret output.
- **On-demand context**: all validated audit reports and current diff.
- **Kill/defer criteria**: keep fake SQL coverage without a current executable replacement; stop on public contract drift.
- **Eval/repair signal**: runtime no longer owns operator queries; net-negative tests; exact contracts pass.
- **Status**: [x]

### Task 10 — Verify, independently validate, document, and close

- **File(s)**: `src/parallax/domains/token_intel/queries/event_token_projection_query.py`; `src/parallax/platform/db/alembic/versions/20260722_0188_token_radar_factor_cache_hard_cut.py`; `tests/unit/test_event_token_projection.py`; `tests/unit/test_postgres_schema.py`; `tests/integration/test_postgres_schema_runtime.py`; `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit`; `docs/reviews/backend-kiss-hard-cut-implementation-audit-zh-2026-07-22.md`; `docs/DESIGN_DISCIPLINE.md`; `docs/references/POSTGRES_PERFORMANCE.md`; `docs/generated/sdd-work-index.md`; `docs/generated/cli-help.md`; `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-10.md`; `docs/generated/subagent-reports/backend-kiss-deep-audit-task-10.md`
- **Owner**: parent plus independent review-only validator
- **Depends on**: Task 6-9
- **Touch set**: `src/parallax/domains/token_intel/queries/event_token_projection_query.py`; `src/parallax/platform/db/alembic/versions/20260722_0188_token_radar_factor_cache_hard_cut.py`; `tests/unit/test_event_token_projection.py`; `tests/unit/test_postgres_schema.py`; `tests/integration/test_postgres_schema_runtime.py`; `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit`; `docs/reviews/backend-kiss-hard-cut-implementation-audit-zh-2026-07-22.md`; `docs/DESIGN_DISCIPLINE.md`; `docs/references/POSTGRES_PERFORMANCE.md`; `docs/generated/sdd-work-index.md`; `docs/generated/cli-help.md`; `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-10.md`; `docs/generated/subagent-reports/backend-kiss-deep-audit-task-10.md`
- **Conflict set**: `web/**`; `.agents/skills`; `docs/sdd/features/active/2026-07-22-docker-build-contract-fix`; `src/parallax/platform/db/alembic/versions/20260721_0185_backend_kiss_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0186_runtime_projection_hard_cut.py`; `src/parallax/platform/db/alembic/versions/20260722_0187_news_fetch_run_fk_index.py`; coordinate with 2026-07-22-news-fetch-retention-index for tests/unit/test_postgres_schema.py and tests/integration/test_postgres_schema_runtime.py; coordinate with 2026-07-23-macro-evidence-ai-hard-cut for all overlapping runtime/domain/API/test/docs paths; coordinate with 2026-07-23-verification-harness-hard-cut for docs/DESIGN_DISCIPLINE.md and docs/generated/sdd-work-index.md
- **Failing test first**: `uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py` — final integration must preserve the compact root architecture contract.
- **Subagent handoff**: `docs/generated/subagent-handoffs/backend-kiss-deep-audit-task-10.md`
- **Subagent report**: `docs/generated/subagent-reports/backend-kiss-deep-audit-task-10.md`
- **Review result**: accepted
- **Implementation**: run the authorized targeted/static gates, audit the final diff and LOC, merge to `main`, build/start the Docker stack, verify real runtime/database/HTTP/WS evidence, repair the two live-only read/cache defects without compatibility glue, obtain a PASS/WARN/FAIL implementation validation, and record every omitted `make check-all` lane without weakening the gate.
- **Verification**: `make docker-status`
- **Review owner**: independent validator then parent
- **Factory lane**: Final integration
- **Deterministic constraints**: no hidden skips or claims beyond evidence; preserve conflict set.
- **On-demand context**: spec/plan/diff/test output and implementation audit.
- **Kill/defer criteria**: unresolved required regression prevents completion; unavailable live/physical evidence is explicitly recorded rather than fabricated.
- **Eval/repair signal**: final validator result and exact completion-gate evidence.
- **Status**: [x]
