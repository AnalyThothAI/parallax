# Tasks — Macro Decision Console

**Status**: Draft
**Superseded by**: Not superseded
**Owning plan**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
**Worktree**: `.worktrees/macro-decision-console`
**Branch**: `codex/macro-decision-console`
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below are TDD ordered. |
| Verify | `verification.md` captures command output. |

## Tasks

### Task 1 — Establish Worktree And Baseline

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: none
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `src/**; web/src/**; coordinate with macrodata-cli for external macrodata files; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Create `.worktrees/macro-decision-console`, verify branch/status, run pre-flight diagnostics, and record redacted config/status summaries in verification.
- **Verification**: `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q`
- **Review owner**: parent agent
- **Factory lane**: Spec/plan
- **Deterministic constraints**: Never print secrets; report only redacted booleans, paths, counts, and exit statuses.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/SECURITY.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Worktree creation fails because branch already exists and cannot be safely reused.
- **Eval/repair signal**: Baseline command failure with unknown cause.
- **Status**: [ ]

### Task 2 — Add Macro Module Hard-Deletion Tests

- **File(s)**: `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/test_macro_module_catalog.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add tests before changing the catalog. Assert retained ids match the allowlist, deleted ids are absent, and retained `related_routes` never point to deleted ids.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests must not introduce hidden/deferred route tiers or direct-link compatibility expectations.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Kill/defer criteria**: Existing module catalog API cannot delete weak ids without a broader contract decision.
- **Eval/repair signal**: Test failure indicates a retained route still links to a deleted route or a deleted route remains registered.
- **Status**: [ ]

### Task 3 — Delete Weak Macro Module Catalog Entries

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Owner**: parent agent
- **Depends on**: Task 2
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Conflict set**: `web/src/features/macro/model/macroNavigationTree.ts; src/parallax/app/surfaces/api/routes_macro.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Remove proxy-only module ids/configs and strip them from all related-route lists. Do not add route tier metadata, hidden support, deferred module state, or compatibility aliases.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Retained module ids remain stable; deleted module ids behave the same as unknown ids.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Deleted modules are still referenced by a required current UI test after Task 2 has been updated.
- **Eval/repair signal**: Existing route tests fail because frontend descriptors still expect deleted labels.
- **Status**: [ ]

### Task 4 — Add Decision Console Unit Tests

- **File(s)**: `tests/unit/domains/macro_intel/test_macro_scenario_engine.py`, `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/test_macro_scenario_engine.py`, `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py; src/parallax/domains/macro_intel/services/macro_regime_engine.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add fixture observations for rates, liquidity, volatility, credit, and assets; assert top changes, confirmations, contradictions, invalidations, watch triggers, trade map, and data blockers are present and human-readable.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: No LLM calls; no wall-clock-sensitive assertions except injected `computed_at_ms`.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Kill/defer criteria**: Existing scenario output already contains all needed fields and only API/frontend shaping is required.
- **Eval/repair signal**: Raw gap codes or empty labels appear in expected user-facing fields.
- **Status**: [ ]

### Task 5 — Implement Decision Console Fields

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Owner**: parent agent
- **Depends on**: Task 4
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Conflict set**: `src/parallax/app/surfaces/api/routes_macro.py; web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add deterministic decision-console shaping from existing features, chain, panels, triggers, and gaps. Add one current nested section for new fields and do not keep duplicate compatibility field names.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No new worker, no new table, no frontend scoring.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Required fields cannot be derived from current persisted snapshot without changing storage shape.
- **Eval/repair signal**: Snapshot payload hash or publication tests fail unexpectedly.
- **Status**: [ ]

### Task 6 — Add API Deleted-Route Tests

- **File(s)**: `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 5
- **Touch set**: `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`
- **Conflict set**: `src/parallax/app/surfaces/api/routes_macro.py; src/parallax/domains/macro_intel/services/macro_module_views.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add tests using existing repository/session fixtures. Assert `/api/macro` exposes decision-console data and deleted module ids use the ordinary not-found path with no deferred/compatibility payload.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: API tests read fixture snapshots, not runtime DB.
- **On-demand context**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Kill/defer criteria**: There is no existing route fixture and adding one would exceed this feature.
- **Eval/repair signal**: API response omits decision-console fields or renders deleted pages as legacy modules.
- **Status**: [ ]

### Task 7 — Implement API And Module View Hard Deletion

- **File(s)**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Owner**: parent agent
- **Depends on**: Task 6
- **Touch set**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Conflict set**: `web/src/features/macro/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Surface decision-console data from persisted snapshots and remove any module-view branches for deleted ids. Deleted ids must not return a special unavailable/deferred payload.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: API must not call macrodata or external providers.
- **On-demand context**: `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Contract change requires generated OpenAPI updates outside current task.
- **Eval/repair signal**: Frontend typecheck fails because generated/handwritten contract types need updates.
- **Status**: [ ]

### Task 8 — Add Frontend Navigation And Overview Tests

- **File(s)**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`
- **Owner**: parent agent
- **Depends on**: Task 7
- **Touch set**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`
- **Conflict set**: `web/src/features/macro/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `web/tests/routes/macro.route.test.tsx::removed macro routes are not registered`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add tests for reduced navigation, overview decision-console order, deleted URLs not registered, and absence of raw gap codes.
- **Verification**: `cd web && npm run test -- web/tests/component/features/macro/MacroModulePages.test.tsx web/tests/routes/macro.route.test.tsx web/tests/unit/features/macro/model/macroPageRegistry.test.ts --run`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests use fixtures and MSW; no live HTTP; tests must not expect hidden/deferred route rendering.
- **On-demand context**: `docs/FRONTEND.md`, `web/tests/fixtures/macroFixture.ts`
- **Kill/defer criteria**: Existing fixture types cannot represent decision-console data without contract update.
- **Eval/repair signal**: Test snapshots show raw internal codes, duplicate sections, or deleted route descriptors.
- **Status**: [ ]

### Task 9 — Implement Frontend Hard Deletion And Decision Console

- **File(s)**: `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/model/macroPageRegistry.ts`, `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`, `web/src/features/macro/ui/pages/macroPages.css`
- **Owner**: parent agent
- **Depends on**: Task 8
- **Touch set**: `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/model/macroPageRegistry.ts`, `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`, `web/src/features/macro/ui/pages/macroPages.css`
- **Conflict set**: `web/src/shared/**; web/src/styles/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `web/tests/routes/macro.route.test.tsx::removed macro routes are not registered`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Delete weak route descriptors and hidden-label preservation, render overview as a decision console, and remove deleted-route rendering branches. Keep CSS macro-owned and under harness limits.
- **Verification**: `cd web && npm run test -- web/tests/component/features/macro/MacroModulePages.test.tsx web/tests/routes/macro.route.test.tsx web/tests/unit/features/macro/model/macroPageRegistry.test.ts --run && npm run lint && npm run test:architecture && npm run typecheck`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No route module or presentational component may call `useQuery`, `getApi`, or `postApi` directly.
- **On-demand context**: `docs/FRONTEND.md`
- **Kill/defer criteria**: UI cannot fit mobile without larger shell changes.
- **Eval/repair signal**: CSS architecture harness fails, mobile route smoke shows overlap, or deleted routes still appear in registry output.
- **Status**: [ ]

### Task 10 — Add macrodata Diagnostics And Import Tests

- **File(s)**: `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py; coordinate with macrodata-cli for external macrodata tests; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add Parallax importer tests for provider diagnostics if the external macrodata result contract changes. In the external macrodata-cli repo, add mocked tests for FRED API-key mode, public CSV fallback mode, public CSV timeout diagnostics, and partial bundle provider coverage.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests do not call live FRED, Yahoo, NY Fed, Treasury, or CFTC.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`
- **Kill/defer criteria**: Existing result envelope cannot accept diagnostics without a model change in macrodata-cli.
- **Eval/repair signal**: Bundle coverage loses available non-FRED observations when FRED fails.
- **Status**: [ ]

### Task 11 — Implement macrodata FRED And Bundle Diagnostics

- **File(s)**: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/services/macro_sync_types.py`
- **Owner**: parent agent
- **Depends on**: Task 10
- **Touch set**: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/services/macro_sync_types.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_sync_service.py; coordinate with macrodata-cli for external macrodata implementation; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: In external macrodata-cli, add redacted source-mode diagnostics and bundle coverage summaries. If the diagnostics contract changes, update Parallax importer/types in this task. Do not keep duplicate legacy diagnostics fields.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not print API keys or environment variable values.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/services/macro_sync_types.py`
- **Kill/defer criteria**: Diagnostics require a breaking macrodata-cli result-envelope change that cannot be consumed in this feature.
- **Eval/repair signal**: `macrodata bundle macro-core` becomes slower or less available than baseline.
- **Status**: [ ]

### Task 12 — Documentation And Source Backlog

- **File(s)**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 5, Task 7, Task 9, Task 11
- **Touch set**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`
- **Conflict set**: `AGENTS.md; CLAUDE.md; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Document hard-deleted macro surfaces, decision-console contract, macrodata diagnostics, and the source backlog that remains after this feature. Update external macrodata-cli docs in its repo when diagnostics are implemented.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent agent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: SDD feature directory contains only spec, plan, tasks, and verification.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/DESIGN_DISCIPLINE.md`
- **Kill/defer criteria**: Implementation is split into successor SDD records before docs can truthfully describe shipped behavior.
- **Eval/repair signal**: SDD validator reports unexpected artifacts, false verification, or active task-board size issues.
- **Status**: [ ]

### Task 13 — Final Verification And Browser QA

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 12
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `src/**; web/src/**; coordinate with macrodata-cli for external macrodata verification; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/architecture/test_completion_gates.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Run repository gates, macrodata-cli gates, and browser QA for `/macro` plus retained primary child routes across desktop/mobile. Record command outputs and manual UI evidence.
- **Verification**: `make check-all`
- **Review owner**: parent agent
- **Factory lane**: Final integration
- **Deterministic constraints**: Do not claim completion unless all tasks are `[x]`, skipped test count is zero, and verification records full evidence.
- **On-demand context**: `docs/FRONTEND.md`, `docs/TESTING.md`, `docs/WORKFLOW.md`
- **Kill/defer criteria**: `make check-all` fails for unrelated baseline issues that the user chooses not to address in this feature.
- **Eval/repair signal**: Browser QA finds overlap, blank charts, raw codes, or deleted route reachability failures.
- **Status**: [ ]
