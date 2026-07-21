# Tasks — Signal Pulse Hard Cut And Architecture Simplification

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut/plan.md`
**Worktree**: `.worktrees/signal-pulse-hard-cut`
**Branch**: `codex/signal-pulse-hard-cut`
**Approved by**: delegated goal
**Approved at**: 2026-07-21

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records hard-cut, fact-retention, shared-infrastructure, migration, frontend, and deployment decisions. |
| Checklist | `spec.md` has measurable source/runtime/database/frontend quality gates. |
| Analyze | `plan.md` maps the complete producer-to-consumer chain and destructive scope. |
| Implement | Tasks are ordered RED guard, backend/data, public/shared, frontend, docs/generated, then verification. |
| Verify | `verification.md` records baseline defects, live evidence, command output, browser evidence, and review. |

## Tasks

### Task 1 — Complete architecture inventory and add RED hard-delete guards

- **File(s)**: `tests/architecture/test_signal_pulse_hard_delete.py`, `tests/integration/test_postgres_schema_runtime.py`, `tests/unit/test_postgres_schema.py`, `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut`
- **Owner**: parent with read-only audit subagents
- **Depends on**: none
- **Touch set**: `tests/architecture/test_signal_pulse_hard_delete.py`, `tests/integration/test_postgres_schema_runtime.py`, `tests/unit/test_postgres_schema.py`, `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut`
- **Conflict set**: coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for shared schema and architecture-test ownership
- **Failing test first**: `tests/architecture/test_signal_pulse_hard_delete.py::test_signal_pulse_current_runtime_surface_is_absent` — fails while the Pulse domain/runtime/public/frontend markers exist.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Guard current runtime/public/config/frontend surfaces, not immutable historical migrations or completed SDD evidence; head-schema test must preserve named facts/read models.
- **On-demand context**: repository/domain architecture maps, current worker manifest, OpenAPI, database schema, frontend route shell, active SDD coordination board.
- **Kill/defer criteria**: Stop a deletion if a verified non-Pulse consumer exists; classify it explicitly and preserve the shared capability without Pulse names.
- **Eval/repair signal**: RED static guard, head-schema test, and reviewed producer/writer/consumer inventory.
- **Implementation**: Add hard-delete tripwires and current-head migration expectations before removing implementation.
- **Verification**: `uv run pytest tests/architecture/test_signal_pulse_hard_delete.py tests/unit/test_postgres_schema.py::test_signal_pulse_hard_delete_drops_entire_retired_projection_without_cascade -q`
- **Review owner**: parent
- **Status**: [~]

### Task 2 — Remove Pulse producer, runtime, data plane and agent lane

- **File(s)**: src/parallax/app/runtime/provider_wiring/model_execution.py, src/parallax/app/runtime/provider_wiring/types.py, src/parallax/app/runtime/provider_wiring/__init__.py, src/parallax/app/runtime/worker_manifest.py, src/parallax/app/runtime/db_pool_bundle.py, src/parallax/app/runtime/repository_session.py, src/parallax/app/runtime/job_queue.py, src/parallax/app/runtime/queue_health.py, src/parallax/app/runtime/ops_diagnostics.py, src/parallax/platform/config/settings.py, src/parallax/platform/agent_execution.py, src/parallax/domains/token_intel/services/token_radar_projection.py, config.example.yaml, tests/architecture/test_signal_pulse_hard_delete.py, tests/unit/test_worker_settings.py, tests/unit/test_provider_wiring_agent_execution_gateway.py
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: src/parallax/app/runtime/provider_wiring/model_execution.py, src/parallax/app/runtime/provider_wiring/types.py, src/parallax/app/runtime/provider_wiring/__init__.py, src/parallax/app/runtime/worker_manifest.py, src/parallax/app/runtime/db_pool_bundle.py, src/parallax/app/runtime/repository_session.py, src/parallax/app/runtime/job_queue.py, src/parallax/app/runtime/queue_health.py, src/parallax/app/runtime/ops_diagnostics.py, src/parallax/platform/config/settings.py, src/parallax/platform/agent_execution.py, src/parallax/domains/token_intel/services/token_radar_projection.py, config.example.yaml, tests/architecture/test_signal_pulse_hard_delete.py, tests/unit/test_worker_settings.py, tests/unit/test_provider_wiring_agent_execution_gateway.py
- **Conflict set**: coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for shared runtime, config, Token Radar and architecture tests
- **Failing test first**: `tests/architecture/test_signal_pulse_hard_delete.py::test_signal_pulse_current_runtime_surface_is_absent` — rejects the domain, worker, producer fan-out, lane, config, provider, repository, queue and diagnostic surfaces.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No Pulse flag/placeholder/ignored setting; preserve News agent lanes, Token Radar stable publication, Narrative wake/catch-up, and material fact repositories.
- **On-demand context**: `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/AGENT_EXECUTION.md`, Token Radar and Pulse domain maps.
- **Kill/defer criteria**: Preserve a shared primitive only when a current non-Pulse import and behavior test prove ownership; rename only if Pulse-specific naming leaks into shared code.
- **Eval/repair signal**: runtime/config/worker/Token Radar targeted tests, import collection, static residual scan, and one-writer manifest tests.
- **Implementation**: Delete Pulse implementation and remove every producer/runtime/config/repository/provider/agent-lane connection.
- **Verification**: `uv run pytest tests/architecture/test_signal_pulse_hard_delete.py tests/architecture/test_worker_inventory_contract.py tests/architecture/test_agent_execution_plane_contracts.py tests/unit/test_worker_settings.py tests/unit/test_provider_wiring_agent_execution_gateway.py -q`
- **Review owner**: parent
- **Status**: [~]

### Task 3 — Remove Pulse public, notification and database contracts

- **File(s)**: src/parallax/app/surfaces/api/schemas.py, src/parallax/app/surfaces/api/validators.py, src/parallax/app/surfaces/cli/commands/queue_ops.py, src/parallax/app/surfaces/cli/dependencies.py, src/parallax/app/surfaces/cli/parser.py, src/parallax/domains/notifications/services/notification_rules.py, src/parallax/platform/db/alembic/versions/20260721_0184_signal_pulse_hard_delete.py, tests/architecture/test_signal_pulse_hard_delete.py, tests/integration/test_postgres_schema_runtime.py, tests/integration/test_api_http.py, tests/integration/test_cli.py, tests/unit/test_postgres_schema.py, tests/unit/test_notification_rules.py
- **Owner**: parent
- **Depends on**: Tasks 1-2
- **Touch set**: src/parallax/app/surfaces/api/schemas.py, src/parallax/app/surfaces/api/validators.py, src/parallax/app/surfaces/cli/commands/queue_ops.py, src/parallax/app/surfaces/cli/dependencies.py, src/parallax/app/surfaces/cli/parser.py, src/parallax/domains/notifications/services/notification_rules.py, src/parallax/platform/db/alembic/versions/20260721_0184_signal_pulse_hard_delete.py, tests/architecture/test_signal_pulse_hard_delete.py, tests/integration/test_postgres_schema_runtime.py, tests/integration/test_api_http.py, tests/integration/test_cli.py, tests/unit/test_postgres_schema.py, tests/unit/test_notification_rules.py
- **Conflict set**: coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for shared API, CLI, notification and schema contracts
- **Failing test first**: `tests/integration/test_postgres_schema_runtime.py::test_runtime_schema_drops_retired_product_tables` — fails until the new head drops exact retired relations and preserves canonical tables.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Exact FK-safe table list; no `CASCADE`, wildcard DDL, historical migration edits, empty endpoint, redirect, notification shim, or ignored CLI branch.
- **On-demand context**: `docs/CONTRACTS.md`, current OpenAPI/router/parser, notification domain map, Alembic chain, generated database schema.
- **Kill/defer criteria**: Stop migration work if any target relation is referenced by a supported current schema object; resolve with an exact dependency inventory, not `CASCADE`.
- **Eval/repair signal**: isolated upgrade, current-schema relation inventory, API/CLI not-found behavior, notification tests, and OpenAPI drift.
- **Implementation**: Remove public/notification contracts and add the irreversible exact database hard cut including shared-row cleanup.
- **Verification**: `uv run pytest tests/integration/test_postgres_schema_runtime.py::test_runtime_schema_drops_retired_product_tables tests/unit/test_postgres_schema.py::test_signal_pulse_hard_delete_drops_entire_retired_projection_without_cascade tests/integration/test_api_http.py tests/integration/test_cli.py tests/unit/test_notification_rules.py -q`
- **Review owner**: parent
- **Status**: [~]

### Task 4 — Remove Signal Lab frontend and simplify Live route state

- **File(s)**: web/src/features/live/useLiveSelection.ts, web/src/features/live/model/liveMobileTask.ts, web/src/features/live/ui/LivePage.tsx, web/src/features/live/ui/LiveTaskNav.tsx, web/src/routes/live.route.tsx, web/src/routes/shellChromeData.ts, web/src/shared/query/queryKeys.ts, web/src/lib/types/frontend-contracts.ts, web/src/lib/types/openapi.ts, web/src/lib/tokenRadar.ts, web/src/lib/venue.ts, web/src/features/notifications/useNotificationsController.ts, web/src/features/ops/ui/OpsDiagnosticsPage.tsx, web/tests/architecture/signalPulseHardDelete.test.ts
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: web/src/features/live/useLiveSelection.ts, web/src/features/live/model/liveMobileTask.ts, web/src/features/live/ui/LivePage.tsx, web/src/features/live/ui/LiveTaskNav.tsx, web/src/routes/live.route.tsx, web/src/routes/shellChromeData.ts, web/src/shared/query/queryKeys.ts, web/src/lib/types/frontend-contracts.ts, web/src/lib/types/openapi.ts, web/src/lib/tokenRadar.ts, web/src/lib/venue.ts, web/src/features/notifications/useNotificationsController.ts, web/src/features/ops/ui/OpsDiagnosticsPage.tsx, web/tests/architecture/signalPulseHardDelete.test.ts
- **Conflict set**: coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for shared frontend contracts; coordinate with 2026-06-16-macro-decision-console for shared shell and generated types; coordinate with 2026-06-18-news-trading-agent-hard-cut for shared shell, notification and generated types
- **Failing test first**: `web/tests/architecture/signalPulseHardDelete.test.ts::deletes the Signal Lab feature and global Live task store` — rejects Signal Lab feature files, Pulse query/contract/selection markers, and a third Live bottom-deck task.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No hidden panel or no-op query; route-local remaining state; preserve Radar/Tape desktop/mobile behavior and shared UI/CSS ownership.
- **On-demand context**: `docs/FRONTEND.md`, Live route/component tests, shell context, notification navigation, frontend architecture harness.
- **Kill/defer criteria**: Stop a shell-state deletion if a current non-Live route consumes it; prove the consumer and preserve the smallest neutral state contract.
- **Eval/repair signal**: frontend architecture/lint/typecheck/component tests plus desktop and mobile browser screenshots.
- **Implementation**: Delete the feature, polling/contracts/fixtures and simplify remaining Live state/navigation ownership.
- **Verification**: `cd web && npm run lint && npm run test:architecture && npm run typecheck && npm run test -- --run tests/component/features/live/ui/LivePage.routing.test.tsx tests/routes/notifications.route.test.tsx`
- **Review owner**: parent
- **Status**: [~]

### Task 5 — Align canonical docs, audit and generated artifacts

- **File(s)**: docs/ARCHITECTURE.md, docs/CONTRACTS.md, docs/FRONTEND.md, docs/RELIABILITY.md, docs/WORKERS.md, docs/WORKER_FLOW.md, docs/AGENT_EXECUTION.md, docs/references/POSTGRES_PERFORMANCE.md, docs/TECH_DEBT.md, src/parallax/domains/token_intel/ARCHITECTURE.md, src/parallax/domains/notifications/ARCHITECTURE.md, docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md, docs/generated/openapi.json, docs/generated/db-schema.md, docs/generated/cli-help.md, docs/generated/sdd-work-index.md, docs/sdd/features/active/2026-06-12-kappa-cqrs-governance-root-fix/spec.md, docs/sdd/features/active/2026-06-12-kappa-cqrs-governance-root-fix/plan.md
- **Owner**: parent
- **Depends on**: Tasks 2-4
- **Touch set**: docs/ARCHITECTURE.md, docs/CONTRACTS.md, docs/FRONTEND.md, docs/RELIABILITY.md, docs/WORKERS.md, docs/WORKER_FLOW.md, docs/AGENT_EXECUTION.md, docs/references/POSTGRES_PERFORMANCE.md, docs/TECH_DEBT.md, src/parallax/domains/token_intel/ARCHITECTURE.md, src/parallax/domains/notifications/ARCHITECTURE.md, docs/reviews/signal-pulse-hard-cut-architecture-audit-zh-2026-07-21.md, docs/generated/openapi.json, docs/generated/db-schema.md, docs/generated/cli-help.md, docs/generated/sdd-work-index.md, docs/sdd/features/active/2026-06-12-kappa-cqrs-governance-root-fix/spec.md, docs/sdd/features/active/2026-06-12-kappa-cqrs-governance-root-fix/plan.md
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared generated SDD index; coordinate with 2026-06-11-executable-harness-followup for shared generated SDD index and validator state; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for shared canonical docs and active SDD validation; coordinate with 2026-06-16-macro-decision-console for shared generated artifacts; coordinate with 2026-06-18-news-trading-agent-hard-cut for shared contracts and generated artifacts
- **Failing test first**: `tests/architecture/test_signal_pulse_hard_delete.py::test_architecture_audit_records_measured_hard_cut_evidence` — requires measured code/database/request/Kappa evidence and keep/remove/defer decisions.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Current docs contain no supported Pulse contract; historical evidence remains clearly historical; generated outputs come from repository generators, not hand edits.
- **On-demand context**: canonical docs, generator commands, live read-only PostgreSQL evidence, before/after diff inventory, SDD validator output.
- **Kill/defer criteria**: Do not delete immutable historical migrations/completed records merely to satisfy a string scan; scope current-contract guards correctly.
- **Eval/repair signal**: docs architecture tests, regen drift checks, SDD validation/index, measured audit completeness, residual scan.
- **Implementation**: Update supported architecture/contracts, write the Chinese audit, remove obsolete generated reports, regenerate canonical artifacts, and repair the pre-existing SDD numbering defect.
- **Verification**: `uv run pytest tests/architecture/test_signal_pulse_hard_delete.py tests/architecture/test_public_contracts_doc_alignment.py tests/integration/test_docs_generated.py -q && make regen-check && uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent
- **Status**: [~]

### Task 6 — Full gates, UI smoke and independent implementation review

- **File(s)**: docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut/verification.md
- **Owner**: parent
- **Depends on**: Tasks 1-5
- **Touch set**: `docs/sdd/features/active/2026-07-21-signal-pulse-hard-cut/verification.md`
- **Conflict set**: coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for repository-wide verification state
- **Failing test first**: tests/architecture/test_signal_pulse_hard_delete.py::test_signal_pulse_current_runtime_surface_is_absent — completion is rejected until hard-delete guards and the full repository gate pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Factory lane**: Final integration
- **Deterministic constraints**: Fresh full command output, no hidden skipped failures, no unreviewed generated drift, no mutation of the real operator database/config, and no claim based only on static scans.
- **On-demand context**: final diff, spec/plan, targeted command results, frontend browser state, migration upgrade output, residual references.
- **Kill/defer criteria**: Keep the SDD active if full gates, browser smoke, migration test, or independent review is incomplete.
- **Eval/repair signal**: `make check-all`, desktop/mobile screenshots, `git diff --check`, residual scan, and validator findings.
- **Implementation**: Repair verified defects, capture final evidence, and move the SDD to completed only after all requirements pass.
- **Verification**: `make check-all`
- **Review owner**: parent
- **Status**: [~]
