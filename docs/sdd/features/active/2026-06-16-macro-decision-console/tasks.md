# Tasks — Macro Decision Console

**Status**: In progress
**Superseded by**: Not superseded
**Owning plan**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
**Worktree**: `.worktrees/macro-decision-console`
**Branch**: `codex/macro-decision-console`
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16

## Gate Compliance

| Gate      | Evidence                                       |
| --------- | ---------------------------------------------- |
| Clarify   | `spec.md` includes `## Clarifications`.        |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze   | `plan.md` includes `## Analyze Gate`.          |
| Implement | Tasks below are TDD ordered.                   |
| Verify    | `verification.md` captures command output.     |

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
- **Review result**: parent-reviewed
- **Implementation**: Create `.worktrees/macro-decision-console`, verify branch/status, run pre-flight diagnostics, and record redacted config/status summaries in verification.
- **Verification**: `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q`
- **Review owner**: parent agent
- **Factory lane**: Spec/plan
- **Deterministic constraints**: Never print secrets; report only redacted booleans, paths, counts, and exit statuses.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/SECURITY.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Worktree creation fails because branch already exists and cannot be safely reused.
- **Eval/repair signal**: Baseline command failure with unknown cause.
- **Status**: [x]

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
- **Status**: [~]

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
- **Status**: [~]

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
- **Implementation**: Add fixture observations for rates, liquidity, volatility, credit, and assets; assert top changes, confirmations, contradictions, invalidations, watch triggers, trade map, two-week scenario cases, and data blockers are present and human-readable.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: No LLM calls; no wall-clock-sensitive assertions except injected `computed_at_ms`.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Kill/defer criteria**: Existing scenario output already contains all needed fields and only API/frontend shaping is required.
- **Eval/repair signal**: Raw gap codes or empty labels appear in expected user-facing fields.
- **Status**: [~]

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
- **Implementation**: Add deterministic decision-console shaping from existing features, chain, panels, triggers, and gaps. Add one current nested section for new fields and do not keep duplicate compatibility field names. The 2026-06-17 continuation adds `scenario_cases` for base/upside/downside two-week trade planning with probability, thesis, trade, entry, stop, and invalidation.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No new worker, no new table, no frontend scoring.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Required fields cannot be derived from current persisted snapshot without changing storage shape.
- **Eval/repair signal**: Snapshot payload hash or publication tests fail unexpectedly.
- **Status**: [~]

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
- **Implementation**: Add tests using existing repository/session fixtures. Assert `/api/macro` exposes decision-console data, including current scenario-case planning when present, and deleted module ids use the ordinary not-found path with no deferred/compatibility payload.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: API tests read fixture snapshots, not runtime DB.
- **On-demand context**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Kill/defer criteria**: There is no existing route fixture and adding one would exceed this feature.
- **Eval/repair signal**: API response omits decision-console fields or renders deleted pages as legacy modules.
- **Status**: [~]

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
- **Status**: [~]

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
- **Implementation**: Add tests for reduced navigation, overview decision-console order, two-week scenario-case rendering, deleted URLs and bare category aliases not registered, and absence of raw gap codes.
- **Verification**: `cd web && npm run test -- web/tests/component/features/macro/MacroModulePages.test.tsx web/tests/routes/macro.route.test.tsx web/tests/unit/features/macro/model/macroPageRegistry.test.ts --run`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests use fixtures and MSW; no live HTTP; tests must not expect hidden/deferred route rendering.
- **On-demand context**: `docs/FRONTEND.md`, `web/tests/fixtures/macroFixture.ts`
- **Kill/defer criteria**: Existing fixture types cannot represent decision-console data without contract update.
- **Eval/repair signal**: Test snapshots show raw internal codes, duplicate sections, or deleted route descriptors.
- **Status**: [~]

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
- **Implementation**: Delete weak route descriptors, bare category redirect aliases, and hidden-label preservation; render overview as a decision console, including backend-supplied two-week scenario cases; and remove deleted-route rendering branches. Keep CSS macro-owned and under harness limits.
- **Verification**: `cd web && npm run test -- web/tests/component/features/macro/MacroModulePages.test.tsx web/tests/routes/macro.route.test.tsx web/tests/unit/features/macro/model/macroPageRegistry.test.ts --run && npm run lint && npm run test:architecture && npm run typecheck`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No route module or presentational component may call `useQuery`, `getApi`, or `postApi` directly.
- **On-demand context**: `docs/FRONTEND.md`
- **Kill/defer criteria**: UI cannot fit mobile without larger shell changes.
- **Eval/repair signal**: CSS architecture harness fails, mobile route smoke shows overlap, or deleted routes still appear in registry output.
- **Status**: [~]

### Task 10 — Add macrodata Diagnostics Tests

- **File(s)**: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`, `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`, `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata tests; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_rates_core_bundle_exposes_missing_api_key_diagnostics tests/unit/test_bundles.py::test_rates_core_bundle_marks_all_series_missing_unavailable tests/cli/test_bundle_commands.py::test_rates_core_without_fred_api_key_uses_public_csv tests/cli/test_bundle_commands.py::test_rates_core_all_series_failing_is_unavailable -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: In the external macrodata-cli repo, add mocked tests for FRED API-key mode, public CSV fallback mode, public CSV timeout diagnostics, and provider-level bundle coverage summaries.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests do not call live FRED, Yahoo, NY Fed, Treasury, or CFTC.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`
- **Kill/defer criteria**: Existing result envelope cannot accept diagnostics without a model change in macrodata-cli.
- **Eval/repair signal**: Bundle coverage loses available non-FRED observations when FRED fails.
- **Status**: [~]

### Task 11 — Implement macrodata FRED And Bundle Diagnostics

- **File(s)**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/errors.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Owner**: parent agent
- **Depends on**: Task 10
- **Touch set**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/errors.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata implementation; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_rates_core_bundle_exposes_missing_api_key_diagnostics tests/cli/test_bundle_commands.py::test_rates_core_all_series_failing_is_unavailable -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add redacted `access_mode` details to FRED successes and errors; add `source_health` to bundle snapshots with provider requested/available/missing/status/error-code/retryability summaries. Do not keep duplicate legacy diagnostics fields.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py tests/provider/test_fred_provider.py tests/cli/test_bundle_commands.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not print API keys or environment variable values.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`
- **Kill/defer criteria**: Diagnostics require a breaking macrodata-cli result-envelope change that cannot be consumed in this feature.
- **Eval/repair signal**: `macrodata bundle macro-core` becomes slower or less available than baseline.
- **Status**: [~]

### Task 12 — Documentation And Source Backlog

- **File(s)**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 5, Task 7, Task 9, Task 11, Task 14
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
- **Status**: [~]

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
- **Status**: [~]

### Task 14 — Add macrodata Official Calendar Bundle

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 10, Task 11
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata provider/bundle changes; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_runtime.py::test_runtime_wires_official_calendar_provider tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add a new `official_calendar` provider for Federal Reserve FOMC calendar HTML and BEA release-date JSON. Add a separate default `macro-calendar-core` bundle containing reachable FOMC, GDP, and PCE next-event series. Task 34 extends the same bundle with BLS CPI, Employment Situation, and PPI official schedule pages. Use event date as `observed_at`, `days_until` as value, and source/time/title metadata in provenance. Do not add these series to `macro-core`.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q && uv run ruff check .`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official public Fed/BEA/BLS sources; no paid feeds, no scraping of unofficial economic calendars, no Parallax compatibility import path, and no Parallax import of calendar observations into numeric `macro-core`.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/AGENTS.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/official_calendar.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Kill/defer criteria**: Official source pages stop exposing parsable public release dates or Parallax ingestion requires a new non-numeric event fact table.
- **Eval/repair signal**: `macro-calendar-core` appears in `macro-core`, the default bundle becomes partial for reachable official schedule pages, `days_until` is non-deterministic in CLI bundle runs, or provenance omits official source URLs.
- **Status**: [~]

### Task 15 — Delete Runtime Static Source-Backlog Gaps

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_gap_payloads.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 7, Task 9
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_gap_payloads.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_has_no_static_source_backlog_gap_codes tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes -q && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Remove all static source-backlog `gap_codes` from retained module configs. Delete backend catalog-gap label/remediation dictionaries for retired source backlog codes so old codes fall through to generic data-gap handling. Remove frontend `rates/expectations` proxy-readiness branching driven by `fed_funds_futures_missing` / `fomc_probability_feed_missing`, and remove those future gaps from macro fixtures. Keep actual missing/stale observation gaps and chart concept gaps intact.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_daily_brief.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Source backlog stays in SDD/spec docs only; runtime module pages must not emit future-integration gaps for unavailable products, and frontend must not maintain special labels or proxy-page states for those retired codes.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/FRONTEND.md`
- **Kill/defer criteria**: A retained module becomes unable to report real missing observations without static backlog gaps.
- **Eval/repair signal**: Any retained module has non-empty static `gap_codes`, raw retired source-backlog codes appear in product text, or `rates/expectations` renders as a proxy/deferred page because of unavailable Fed futures/FOMC probability sources.
- **Status**: [~]

### Task 16 — Add macrodata Treasury Auction Result Bundle

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 10, Task 11
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata provider/bundle changes; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_http_client.py::test_http_client_disables_environment_proxy_settings tests/provider/test_treasury_auction_provider.py tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_runtime_wires_treasury_auction_provider tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_treasury_auction_core_bundle_fetch_uses_official_fiscaldata -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add `treasury_auction` provider backed by the official U.S. Treasury FiscalData `auctions_query` API. Disable `httpx` environment proxy use in `MacrodataHttpClient` because the project runtime succeeds with `trust_env=False` while `trust_env=True` times out on FiscalData TLS handshake. Add standalone `treasury-auction-core` for completed 2Y/10Y/30Y auction high yield, bid-to-cover, and indirect bidder accepted percentage. Do not add these event observations to numeric `macro-core`, and do not restore the Parallax `rates/auctions` route in this task.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q && uv run ruff check . && uv run macrodata bundle fetch treasury-auction-core --asof 2026-06-16`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Treasury FiscalData; no paid feeds, no unofficial auction calendar scraping, no auction-tail calculation without a reliable when-issued yield source, no Parallax compatibility import path, and no Parallax import of auction observations into numeric `macro-core`.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/treasury_auction.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/gateway/http_client.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Kill/defer criteria**: FiscalData auction query becomes unreachable from the project runtime or does not expose completed auction result fields needed for high yield, bid-to-cover, and indirect bidder share.
- **Eval/repair signal**: `treasury-auction-core` appears in `macro-core`, live smoke returns partial/unavailable for current 2Y/10Y/30Y result metrics, or a deleted auction page route is restored instead of keeping auction results in event-aware overview rendering.
- **Status**: [~]

### Task 17 — Import And Render Official Macro Events

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 16
- **Touch set**: `src/parallax/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_api_macro_contract.py`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap; coordinate with macrodata-cli for external event bundle contracts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_event_targets_refresh_without_numeric_snapshot tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q && cd web && npm run test -- MacroModulePages.test.tsx -t "renders overview page grammar" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add event-provider series mappings for `macro-calendar-core` and `treasury-auction-core` that are importable into `macro_observations` as `event:*` concepts while remaining outside numeric `MACRO_CORE_CONCEPTS`. Let `MacroViewProjectionWorker` refresh event-only series rows without rebuilding the `macro_regime_v4` snapshot. Add overview module event concepts, backend `decision_console.event_catalysts`, and frontend rendering in the existing decision console.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py -q && cd web && npm run test -- MacroModulePages.test.tsx MacroRatesWorkbench.test.tsx macroPageRegistry.test.ts macroRoutes.test.ts --run && npm run lint && npm run test:architecture && npm run typecheck`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add event observations to `macro-core`, do not expand numeric readiness/scoring counts, do not restore `rates/auctions` or any deleted Fed/calendar proxy page, and do not let the frontend derive catalyst text from raw series values.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/official_calendar.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/treasury_auction.py`
- **Kill/defer criteria**: Event observations require a new persistent table or scheduled multi-bundle runtime orchestration beyond the current import/projection path.
- **Eval/repair signal**: `event:*` concepts appear in `MACRO_CORE_CONCEPTS`, event-only dirty targets rebuild numeric snapshots, deleted macro routes reappear, or the overview decision console shows raw provider keys instead of readable catalysts.
- **Status**: [~]

### Task 18 — Schedule Official Event Bundles In Macro Sync

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_sync_service.py`, `src/parallax/platform/config/settings.py`, `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `src/parallax/app/runtime/worker_manifest.py`, `tests/unit/domains/macro_intel/test_macro_sync_service.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`, `tests/architecture/test_worker_runtime_contracts.py`, `docs/SETUP.md`, `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 16, Task 17
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/**`, `src/parallax/platform/config/settings.py`, `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `src/parallax/app/runtime/worker_manifest.py`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`, `tests/architecture/test_worker_runtime_contracts.py`, `docs/SETUP.md`, `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `coordinate with macrodata-cli for external event history command changes; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces tests/unit/test_bundles.py::test_bundle_history_marks_empty_series_windows_unavailable -q && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && uv run pytest tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_schedules_all_configured_product_bundles tests/unit/test_worker_settings.py::test_default_workers_yaml_contains_canonical_worker_defaults tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_configured_sync_bundles -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add first-class `macrodata bundle history macro-calendar-core` and `macrodata bundle history treasury-auction-core` CLI surfaces. Mark bundle-history windows with zero observations as `unavailable`/`no_observations` instead of `ok`. Replace Parallax `workers.macro_sync.bundle_name` with formal `bundle_names`; Task 17 defaulted it to `macro-core`, `macro-calendar-core`, and `treasury-auction-core`, and Task 31 extends the current default with `fed-text-core`. `MacroSyncService.enqueue_due_windows` schedules each configured bundle through the existing `macro_sync_windows` table. Extend macrodata runtime diagnostics so `macro status` reports missing configured sync bundles when the installed `macrodata-cli` package is stale. Pin Parallax to macrodata-cli Git rev `c59b298994d111f36b4eef292790714057db42c0` so normal `uv run` installs the event-history-capable package for the Task 17 bundles.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/cli/test_bundle_commands.py tests/unit/test_bundles.py tests/provider/test_official_calendar_provider.py tests/provider/test_treasury_auction_provider.py -q && uv run ruff check src/macrodata/surfaces/cli.py src/macrodata/app/services.py tests/cli/test_bundle_commands.py tests/unit/test_bundles.py && uv run macrodata bundle history macro-calendar-core --start 2026-06-16 --end 2026-07-31 && uv run macrodata bundle history treasury-auction-core --start 2026-05-01 --end 2026-06-16 && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && uv run pytest tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_scheduler.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_sync_service.py src/parallax/platform/config/settings.py src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No service fallback to old `bundle_name`; no host-local macrodata checkout dependency in Parallax runtime; no restored macro proxy pages; event bundles remain outside numeric `macro-core` and numeric readiness.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/WORKERS.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/surfaces/cli.py`
- **Kill/defer criteria**: The packaged macrodata release cannot expose event bundle history commands, or operators decide event catalysts should stay manual import only.
- **Eval/repair signal**: `macro_sync` only schedules `macro-core`, old `bundle_name` remains a runtime setting, `macro status` cannot identify stale macrodata packages missing event bundles, or zero-observation event history windows report `ok`.
- **Status**: [~]

### Task 19 — Record Timsun Parity Audit And Successor Source Plan

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`, `docs/TECH_DEBT.md`
- **Owner**: parent agent
- **Depends on**: Task 12, Task 18
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/**`, `docs/TECH_DEBT.md`
- **Conflict set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/**; docs/TECH_DEBT.md`
- **Failing test first**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Capture the live retained-module audit and timsun benchmark read. Split remaining parity work into source-backed successor tasks: trade-map reliability, Fed text lane, rate probabilities, volatility term structure, crypto derivatives, options/GEX/breadth, global-dollar funding, subsurface funding, credit microstructure, and economy nowcast/surprise. Keep the source backlog in docs only; do not add hidden routes, static runtime gap labels, or compatibility code for deleted pages.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check`
- **Review owner**: parent agent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Source candidates must distinguish public official feeds from paid/licensed feeds; no secret values, scraped-workaround assumptions, restored deleted routes, or frontend proxy states.
- **On-demand context**: `docs/SECURITY.md`, `docs/DESIGN_DISCIPLINE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: A source cannot be legally or technically evaluated enough to classify public vs paid, in which case it stays `research required` and no route is restored.
- **Eval/repair signal**: SDD docs advertise parity without a source, route compatibility code reappears, or current live audit contradicts the retained-module readiness claim.
- **Status**: [~]

### Task 20 — Add Trade Map And Asset Cross-Asset Historical Review

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; src/parallax/app/surfaces/api/routes_macro.py; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_asset_class_diagnostics_from_module_history -q`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders bonds asset-class diagnostics"`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders fx asset-class diagnostics"`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders crypto asset-class diagnostics"`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add a backend-only five-asset 60-day historical review to overview `decision_console.trade_map` for `NDX`, `BTC`, `GOLD`, `SPX`, and `TLT`. Load these histories through the overview module API using the existing macro observation projection, not frontend provider calls. Render compact history lines in the Trade Map panel and add explicit HY OAS widening/tightening labels so the overview does not show `待确认信号` for known rules. The 2026-06-17 continuations also add backend `asset_diagnostics` to retained `assets` for SPX, TLT, DXY, WTI, BTC, VIX, and HY OAS, then render it as `跨资产诊断` directly after the core asset market board; retained `assets/equities` now emits `asset_class_diagnostics` from SPX, NDX, RUT, QQQ, IWM, and CFTC S&P net non-commercial positioning, rendered as `美股风险诊断` directly after the market evidence; retained `assets/bonds` now emits `asset_class_diagnostics` from TLT, IEF, LQD, HYG, HY OAS, and IG OAS, rendered as `债券风险诊断` from the backend payload label; retained `assets/commodities` now emits `asset_class_diagnostics` from WTI, Brent, NatGas, Gold, and Copper, rendered as `商品冲击诊断` from the backend payload label; retained `assets/fx` now emits `asset_class_diagnostics` from DXY, Broad USD, EURUSD, USDJPY, USDCNY, and UUP, rendered as `美元压力诊断` from the backend payload label; retained `assets/crypto` now emits `asset_class_diagnostics` from BTC/ETH plus OKX/Deribit OI, funding, basis, and DVOL leverage evidence, rendered as `加密 beta 诊断` from the backend payload label, with missing derivatives groups surfaced as module-reference data-health gaps. These slices use existing projected macro observations and do not restore `assets/crypto-derivatives`, OKX/Deribit derivative shells, options/GEX, standalone CFTC, CDS, commodity proxy shells, or any hidden compatibility route.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_module_read_adds_asset_class_diagnostics_from_module_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_module_read_adds_asset_class_diagnostics_from_module_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_module_read_adds_asset_class_diagnostics_from_module_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_module_read_adds_asset_class_diagnostics_from_module_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_asset_class_diagnostics_from_module_history -q && cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side backtest or macro-regime math, no new provider calls in API request path beyond reading projected macro observation rows, no restored deleted routes, and no hidden compatibility fields.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: Required five-asset histories are unavailable in projected macro observations, or the review requires a new table beyond this slice.
- **Eval/repair signal**: `/macro` lacks five-asset history rows, Trade Map shows `待确认信号` for known HY OAS rules, frontend computes returns locally, overview API returns only latest observations for the Trade Map targets, or `/macro/assets` lacks a backend-fed `跨资产诊断` region despite SPX/TLT/DXY/WTI/BTC/VIX/HY OAS history.
- **Status**: [~]

### Task 21 — Add Trade Map Paper P&L And Action Checklist

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 20
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add a backend-generated `$10K` equal-weight paper map to overview `decision_console.trade_map` whenever the five-asset historical review is available. Report paper P&L, P&L percentage, max adverse dollars, risk temperature, and an action checklist derived from backend confirm/invalidate conditions plus a position-review row. Render the paper map and checklist in the Macro Workbench Trade Map panel without frontend-side P&L math.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check && uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side allocation/P&L/backtest math, no compatibility fields for deleted pages, and no sourced-data claims beyond persisted macro observations.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: The paper map cannot be derived deterministically from existing historical review rows, or it needs execution/broker semantics beyond a display-only decision audit.
- **Eval/repair signal**: `/macro` lacks `$10K` paper map rows, P&L is computed in React, action checklist shows raw codes, or paper P&L is presented as an executable trade.
- **Status**: [~]

### Task 22 — Add Trade Map Historical Trust And Holding-Period Review

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 21
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `historical_trust` and `holding_period_review` to overview `decision_console.trade_map` using the same five source-backed asset histories as the 60-day review. Evaluate 1D, 5D, and 20D holding periods from the first available observation to the first observation at or after each horizon. Render historical trust and holding-period rows in the Macro Workbench Trade Map panel without frontend-side return or P&L math. The 2026-06-17 continuation also structures the Trade Map panel into explicit `当前表达`, `五资产雷达`, `组合复盘`, `历史可信度`, `持有期复盘`, and `行动清单` blocks so the timsun-style reliability evidence is readable instead of a flat text run.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check && uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && git diff --check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side holding-period/backtest math, no new provider calls, no compatibility fields for deleted pages, and no claims beyond persisted macro observations.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: Holding-period review requires prior macro-map storage instead of current five-asset histories, in which case this becomes a successor read-model task.
- **Eval/repair signal**: `/macro` lacks historical trust or 1D/5D/20D holding rows, holding P&L is computed in React, or trust scores are shown without sample counts.
- **Status**: [~]

### Task 23 — Add Yield Curve Curve-Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`, `web/src/features/macro/ui/rates/RatesCurveDiagnostics.tsx`, `web/src/features/macro/ui/rates/RatesRealRateDiagnostics.tsx`, `web/src/features/macro/ui/rates/ratesCurveDiagnostics.css`, `web/src/features/macro/ui/rates/ratesRealRateDiagnostics.css`, `web/src/features/macro/ui/rates/macroRatesWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_module_read_adds_real_rate_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `curve_diagnostics` to `rates/yield-curve` when Treasury histories support it. Calculate 2s10s, 3m10y, and 5s30s current spread plus 1w/1m/3m changes from persisted FRED histories; classify curve shape; emit implication and invalidation text. The 2026-06-17 continuation also emits bounded spread-history series and 5Y/10Y nominal-real-breakeven tenor comparison from existing nominal Treasury, TIPS real-yield, and breakeven histories. The same continuation adds backend-generated `real_rate_diagnostics` to `rates/real-rates` from existing 5Y/10Y/30Y TIPS, 5Y/10Y breakeven, and 5Y5Y forward inflation histories, then renders it as a rates-owned decision block. Render the diagnostics after the primary chart in adjacent owner components/CSS so the route CSS budget stays below the architecture harness limit.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side curve math or macro scoring, no provider calls in React, no restored deleted rates pages, no compatibility fields, and no curve diagnosis when only a single latest point is available.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED nominal Treasury histories are unavailable from the current macro snapshot, or a requested tenor cannot be backed by nominal, real, and breakeven observations.
- **Eval/repair signal**: `rates/yield-curve` lacks a curve-diagnostics region despite source-backed histories, `rates/real-rates` lacks a real-rate diagnostics region despite source-backed TIPS/breakeven histories, display text exposes raw `rates:*` or `inflation:*` keys, source-backed spread-history/tenor/real-yield rows are omitted, curve or real-rate changes are computed in React, or `macroRatesWorkbench.css` exceeds the 500-line CSS architecture budget.
- **Status**: [~]

### Task 24 — Add Credit Stress Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_nfci_tightening_when_spreads_lag -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `credit_diagnostics` to `credit/stress` when persisted FRED/Yahoo credit histories support it. Calculate HY OAS, IG OAS, CCC-HY tail spread, HYG/LQD credit ETF relative pressure, NFCI financial conditions, adjusted NFCI, and SLOOS large-firm tightening current values plus available 1w/1m/3m or 1q changes; classify credit regime, including `credit_etf_pressure` when HYG runs behind LQD before spreads fully confirm and `financial_conditions_tightening` when NFCI tightens before spreads fully confirm; emit implication and invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf page using an adjacent workbench-owned component and CSS file, and display ETF-relative and index-valued credit rows rather than dropping them.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`; 2026-06-17 NFCI and HYG/LQD continuations additionally verified `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/test_api_macro_contract.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q`, `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py`, `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx`, `cd web && npm run typecheck`, `cd web && npm run lint`, and API-equivalent live `credit/stress` module probes against `/Users/qinghuan/.parallax/`.
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side credit math, no provider calls in React, no restored `credit/cds`, no hidden credit route, no compatibility fields, no fabricated CDS/TRACE/ETF-flow placeholder, no JNK duplication while HYG/LQD already cover the tradable public ETF confirmation, and no credit diagnosis when only a single latest point is available.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED credit histories are unavailable from the current macro snapshot, or TRACE/CDS/ETF liquidity evidence requires a broader credit read model.
- **Eval/repair signal**: `credit/stress` lacks a credit-diagnostics region despite source-backed histories, omits `HYG/LQD 信用 ETF` when HYG/LQD history exists, omits `NFCI 金融条件` when NFCI history exists, drops ETF-relative or index-valued credit rows in the frontend, displays raw `credit:*` keys, computes credit changes in React, or CSS architecture breakpoints drift from the frontend harness contract.
- **Status**: [~]

### Task 25 — Add Volatility VIX Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `volatility_diagnostics` to `volatility/vix` when persisted volatility histories can support it. Calculate VIX spot, VIX3M-VIX term premium, VIXY/VIXM front-end pressure, and VXN current values plus 1w/1m changes from module feature histories, then classify volatility regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf module page using an adjacent workbench-owned component and CSS file. The 2026-06-17 Cboe continuations add official Cboe historical CSV provider support in macrodata-cli for `cboe:VVIX`, `cboe:SKEW`, `cboe:VIX9D`, and `cboe:VIX1D`; bump macrodata-cli through `0.1.20` commit `739d0bab59f4ac8b905008478aeefbeb541e4a9b`; repin Parallax to that packaged dependency; map those series to required-history `vol:vvix`, `vol:skew`, `vol:vix9d`, and `vol:vix1d`; fold them into retained `volatility/vix` tiles/table/availability notes; add backend diagnostics rows for convexity, tail premium, `VIX9D-VIX` near-term event premium, and `VIX1D-VIX` same-day event premium; add `cboe -> Cboe` source labels; and make leaf-module API reads use persisted concept history rather than only latest rows.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side volatility math, no provider calls in React, no fake VIXD/VIX1D/VIX9D/VVIX/SKEW rows, no restored volatility dashboard, no compatibility fields, and no volatility diagnosis when only a single latest point is available. MOVE rows must come from persisted `yahoo:^MOVE` macro facts, and VIX1D/VIX9D/VVIX/SKEW rows must come from official Cboe macro facts, not static UI placeholders.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/Cboe/Yahoo volatility histories are unavailable from the current macro snapshot, or true futures/options term-structure evidence requires a broader licensed volatility read model.
- **Eval/repair signal**: `volatility/vix` lacks a volatility-diagnostics region despite source-backed histories, omits VIX1D/VIX9D/VVIX/SKEW after projected Cboe facts exist, displays raw `vol:*` keys or `未知来源` for Cboe facts, computes volatility changes in React, or the deleted volatility dashboard route is restored instead of keeping the source-backed read on the retained VIX module.
- **Status**: [~]

### Task 26 — Add Liquidity RRP/TGA Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `liquidity_diagnostics` to `liquidity/rrp-tga` when persisted liquidity histories can support it. Calculate SOFR-IORB corridor pressure, SOFR-TGCR repo-depth pressure, SOFR underlying volume, RRP buffer, TGA fiscal cash, and net liquidity current values plus 1w/1m changes when enough history exists, then classify liquidity regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf module page. Replace the duplicated credit/volatility-specific diagnostic panels with one shared macro signal diagnostics panel and delete the redundant old components/CSS. The 2026-06-17 continuation adds NY Fed Markets API `BGCR`, `TGCR`, `SOFR_VOLUME`, `BGCR_VOLUME`, and `TGCR_VOLUME` to external macrodata-cli `liquidity-core` / `macro-core`, repins Parallax to macrodata-cli `0.1.16` commit `06b94b1ccf5840ed34205498c4fddd43f796bb9d`, maps the five concepts into `liquidity/rrp-tga`, and makes module views supplement missing snapshot features from projected module observations so freshly projected optional repo-depth facts display before long-history bootstrap completes.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side liquidity math, no provider calls in React, no fake 7d/14d future liquidity heatmap, no restored `liquidity/global-dollar` or `liquidity/subsurface`, no compatibility fields, and no liquidity diagnosis when all rows have only a single latest point. Single-point repo-depth facts may still render as tiles/table rows and diagnostic rows when other liquidity histories support the diagnostic block.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: NY Fed/FRED/Treasury liquidity histories are unavailable from the current macro snapshot, or future Treasury/Fed event heatmap and projected liquidity impact require a broader event read model.
- **Eval/repair signal**: `liquidity/rrp-tga` lacks a liquidity-diagnostics region despite source-backed histories, omits projected NY Fed BGCR/TGCR/volume facts from tiles and tables, displays raw `liquidity:*` keys, computes SOFR-IORB/SOFR-TGCR/net liquidity in React, or a deleted liquidity page is restored instead of keeping the source-backed read on the retained RRP/TGA module.
- **Status**: [~]

### Task 27 — Add Inflation Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_module_read_adds_inflation_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `inflation_diagnostics` to `economy/inflation` when persisted inflation histories can support it. Calculate CPI YoY, Core CPI YoY, PPI YoY, and 10Y breakeven current/change rows from module feature histories, then classify inflation regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board through the generic macro signal diagnostics panel.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side inflation math, no provider calls in React, no fake actual-vs-consensus or surprise rows, no restored economy calendar/surprise page, no compatibility fields, and no inflation diagnosis when yearly history is unavailable.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED inflation histories are unavailable from the current macro snapshot, or surprise/consensus/revision evidence requires a broader licensed or official release read model.
- **Eval/repair signal**: `economy/inflation` lacks an inflation-diagnostics region despite source-backed histories, displays raw `inflation:*` keys, computes YoY inflation in React, or a proxy-only surprise/calendar page is restored instead of keeping the source-backed read on the retained inflation module.
- **Status**: [~]

### Task 28 — Add Employment Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/**`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_module_read_adds_employment_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `employment_diagnostics` to `economy/employment` when persisted labor histories can support it. Calculate unemployment-rate change, payroll monthly gain/deceleration, initial-claims change, job-openings change, and wage YoY/current-change rows from module feature histories, then classify labor-market regime and emit implication/invalidation text. Render the diagnostics between primary market evidence and driver board through the generic macro signal diagnostics panel.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side employment math, no provider calls in React, no fake actual-vs-consensus or payroll surprise rows, no restored economy calendar/surprise page, no compatibility fields, and no employment diagnosis when history is insufficient for monthly change or wage YoY.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/BLS labor histories are unavailable from the current macro snapshot, or consensus/revision/surprise evidence requires a broader official-release or licensed calendar read model.
- **Eval/repair signal**: `economy/employment` lacks an employment-diagnostics region despite source-backed histories, displays raw `labor:*` keys, computes labor-market changes in React, or a proxy-only surprise/calendar page is restored instead of keeping the source-backed read on the retained employment module.
- **Status**: [~]

### Task 29 — Add GDP Growth Diagnostics Workbench

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/**`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `growth_diagnostics` to `economy/gdp` when persisted growth histories can support it. Calculate real GDP YoY/quarterly deceleration, source-backed GDPNow SAAR nowcast, industrial-production YoY/current change, housing-starts level/change, real PCE YoY/current change, and retail-sales YoY/current change from module feature histories, then classify growth regime and emit implication/invalidation text. Render the diagnostics between primary market evidence and driver board through the generic macro signal diagnostics panel. The 2026-06-17 continuation adds `fred:GDPNOW` to external macrodata-cli `economy-core`, repins Parallax to macrodata-cli `0.1.15` commit `a01ed678ad578cd6406f93b20558da4ccd1fc660`, maps it to `economy:gdp_nowcast`, and keeps it optional so missing nowcast history never downgrades global macro readiness.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py tests/unit/test_runtime.py -q && uv run ruff check src tests`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side growth math, no provider calls in React, no fake nowcast, no actual-vs-consensus or surprise rows, no restored `economy/consumer` or separate surprise/calendar page, no compatibility fields, and no growth diagnosis when yearly history or current/quarter change evidence is insufficient.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/BEA/BLS growth histories are unavailable from the current macro snapshot, or consensus/revision/surprise evidence requires a broader official-release or licensed calendar read model.
- **Eval/repair signal**: `economy/gdp` lacks a growth-diagnostics region despite source-backed histories, displays raw `economy:*` or `consumer:*` keys, computes GDP/consumption changes in React, or a proxy-only consumer/surprise page is restored instead of keeping the source-backed read on the retained GDP module.
- **Status**: [~]

### Task 30 — Add Fed Funds Corridor Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`, `web/src/features/macro/ui/rates/RatesPolicyDiagnostics.tsx`, `web/src/features/macro/ui/rates/ratesPolicyDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_nyfed_unsecured_funding_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_absorbs_nyfed_unsecured_funding_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add backend-generated `policy_diagnostics` to `rates/fed-funds` when persisted policy-rate histories can support it. Calculate target range, EFFR position inside the range, EFFR-IORB, SOFR-EFFR, SOFR 30D-EFFR, and DFF/EFFR drift from module feature histories, then classify policy-corridor regime and emit implication/invalidation text. Render the diagnostics between the primary rates visual and decision-support board in the rates workbench. The 2026-06-17 continuation adds NY Fed Markets API `EFFR`, `OBFR`, `EFFR_VOLUME`, and `OBFR_VOLUME` to external macrodata-cli `rates-market-core` / `macro-core`, repins Parallax to macrodata-cli `0.1.17` commit `ac06e171833a99e19761dc69a2e6a222d7f80754`, maps NY Fed EFFR into the existing `fed:effr` concept with higher source priority than the FRED mirror, and folds `fed:obfr`, `fed:effr_volume`, and `fed:obfr_volume` into retained `rates/fed-funds` diagnostics/table evidence instead of restoring any Fed or subsurface route.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`; `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q && uv run ruff check src tests`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_sync_service.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side policy-rate math, no provider calls in React, no fake FedWatch probabilities, no restored Fed statements/speeches, `rates/auctions`, `rates/expectations`, or `liquidity/subsurface` route, no compatibility fields, and no policy diagnosis when current corridor or spread evidence is insufficient. Short-history NY Fed funding-depth concepts are displayable but optional for global history readiness.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: EFFR/IORB/SOFR histories are unavailable from the current macro snapshot, NY Fed unsecured reference-rate endpoints stop returning rate/volume payloads, or meeting-date probability evidence requires an approved CME/Bloomberg/legal source lane.
- **Eval/repair signal**: `rates/fed-funds` lacks a policy-corridor diagnostics region despite source-backed histories, omits OBFR/EFFR/OBFR volume rows after successful NY Fed sync, displays raw `fed:*` or `liquidity:*` keys, computes policy spreads in React, or a proxy-only Fed/FOMC/subsurface page is restored instead of keeping the source-backed read on the retained Fed funds module.
- **Status**: [~]

### Task 31 — Add Official Fed Text Event Bundle

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/platform/config/settings.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_sync_service.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`
- **Owner**: parent agent
- **Depends on**: Task 19, Task 24
- **Touch set**: `src/parallax/domains/macro_intel/**`, `src/parallax/platform/config/settings.py`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_*macro*`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_fed_text_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q`; `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_fed_text_events_with_stable_document_series_keys tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: In the external macrodata-cli checkout, add provider `official_fed_text` and bundle `fed-text-core` for official Federal Reserve FOMC statement, minutes, monetary-policy press-release, and speech documents. Reject legacy aliases such as `fed_page_latest`. In Parallax, map those series to `event:fed_fomc_statement`, `event:fed_fomc_minutes`, `event:fed_monetary_policy_press_release`, and `event:fed_speech`, persist same-day Fed documents under stable URL-derived series keys, render their titles as overview `event_catalysts`, and add `fed-text-core` to the default `workers.macro_sync.bundle_names`.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests && uv run --isolated --with mypy==1.13.0 mypy src tests && uv run pytest -q && uv run macrodata source smoke --provider official_fed_text --format pretty && uv run macrodata bundle fetch fed-text-core --asof 2026-06-16 --format pretty && uv run macrodata bundle history fed-text-core --start 2026-05-08 --end 2026-05-08 --format pretty`; `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q`; `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/platform/config/settings.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Federal Reserve sources; do not scrape/parse unofficial summaries; do not restore `fed/statements` or `fed/speeches`; do not add compatibility aliases; do not put Fed text into numeric `MACRO_CORE_CONCEPTS`; preserve source URL/title/timestamp in provenance; avoid DB uniqueness collisions for same-day speeches.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, macrodata-cli reference catalog in the external checkout
- **Kill/defer criteria**: Federal Reserve official pages/RSS become inaccessible from this runtime, or text delta/scoring is required before catalyst-only rendering can ship.
- **Eval/repair signal**: `fed-text-core` appears as a numeric macro-core concept, deleted Fed routes return a module shell, two speeches on the same date overwrite each other, or live `macro status` cannot identify an installed macrodata package that lacks `fed-text-core`.
- **Status**: [~]

### Task 32 — Repin Fed Text Runtime And Allow Text Event Projection

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/20260616_0180_macro_event_text_series_nullable.py`, `tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/test_postgres_schema.py`
- **Owner**: parent agent
- **Depends on**: Task 31
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/**`, `tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/test_postgres_schema.py`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/repositories/macro_intel_repository.py; src/parallax/platform/db/alembic/versions/**; tests/unit/domains/macro_intel/test_macro_migration_contract.py; coordinate with 2026-06-09-agent-playbook-skill-hard-cut for repository and migration-contract overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py::test_partition_refresh_allows_text_event_rows_without_numeric_values tests/unit/test_postgres_schema.py::test_macro_event_text_series_nullable_migration_allows_text_event_rows -q`; live `uv run parallax macro sync --bundle fed-text-core --start 2026-04-01 --end 2026-06-16`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: In macrodata-cli, add per-request HTTP timeout support and give official Federal Reserve text pages/RSS a longer timeout so the speeches feed does not falsely mark `fed-text-core` partial. In Parallax, repin macrodata-cli to commit `ba8cf292afb77bfd554e0a0ebf1f3d0b0fc040fc`, make `macro_observation_series_rows.value_numeric` nullable, and update the projection refresh query to include non-numeric `event:*` rows while preserving the numeric-only filter for ordinary macro series.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q && uv run ruff check src tests && uv run --isolated --with mypy==1.13.0 mypy src tests && uv run macrodata bundle history fed-text-core --start 2026-04-01 --end 2026-06-16 --format pretty`; `uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/unit/test_postgres_schema.py::test_macro_event_text_series_nullable_migration_allows_text_event_rows -q`; `uv run parallax db migrate`; `uv run parallax macro sync --bundle fed-text-core --start 2026-04-01 --end 2026-06-16`; live overview payload probe for `decision_console.event_catalysts`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add host-local macrodata checkout fallbacks, hidden Fed routes, compatibility aliases, or numeric sentinel values for text events. Text facts remain source-backed `event:*` rows with null `value_numeric`; same-day document identity remains URL-derived in facts.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, external macrodata-cli `official_fed_text` provider
- **Kill/defer criteria**: Federal Reserve official RSS/feed access repeatedly fails even with the extended timeout, or making text event read-model rows nullable breaks current numeric chart paths.
- **Eval/repair signal**: live `fed-text-core` sync reports partial/missing `official_fed_text:speech_latest`, `macro status` reports missing `fed-text-core`, `event:fed_speech` facts are absent after sync, or overview catalysts omit Fed text rows.
- **Status**: [~]

### Task 33 — Make Event Catalysts Inspectable

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 32
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_module_views.py; web/src/features/macro/**; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Preserve `source_url` from official event provenance in overview `event_catalysts`; preserve Fed text `document_type` and speech `speaker` metadata when available; map those fields through the macro workbench model and render primary-source `原文` links in the decision console. Add backend `decision_console.event_heatmap` from upcoming 0-14 day `calendar`/`auction_calendar` catalysts plus recent `fed_text` catalysts, classified by window, severity, category, impact, watch text, and source URL. Render a dedicated `事件热力` section in the existing overview decision panel. Keep auction results in `event_catalysts`, not the heatmap. Keep the Fed text lane catalyst/heatmap-only and do not restore deleted Fed routes, auctions routes, calendar/surprise pages, or text scoring.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366 && cd .. && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend provider calls, no React-side macro or event scoring, no Fed text route restoration, no auctions route restoration, no calendar/surprise route restoration, no hidden compatibility aliases, no auction-tail fabrication, no actual/consensus/surprise placeholders, no numeric sentinel values for text events, and no source URLs invented when provenance lacks one.
- **On-demand context**: `docs/FRONTEND.md`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Official source provenance is absent from imported event rows, or product needs full text-delta scoring before catalyst links are acceptable.
- **Eval/repair signal**: Overview catalysts render titles but lack `source_url`, Fed speech rows lack speaker metadata despite title/provenance support, UI displays a Fed catalyst without a primary-source link when one exists, the heatmap includes `auction_result` or `fed_text`, or a deleted route is restored.
- **Status**: [~]

### Task 34 — Add BLS Official Calendar Catalysts

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 17, Task 33
- **Touch set**: `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/_constants.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Extend macrodata-cli `official_calendar` with official BLS CPI, Employment Situation, and PPI release schedule pages, add those three series to catalog and `macro-calendar-core`, and map them in Parallax to `event:bls_cpi_next`, `event:bls_employment_next`, and `event:bls_ppi_next` metadata. Preserve BLS reference period and release time in provenance. Keep the data catalyst-only in the overview decision console.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official BLS pages, no unofficial economic-calendar scraping, no restored calendar/surprise route, no actual-vs-consensus or surprise fields, no Parallax compatibility alias, and no import of BLS event observations into numeric `MACRO_CORE_CONCEPTS`.
- **On-demand context**: external macrodata-cli official-calendar provider/catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Official BLS schedule pages stop exposing parsable public release rows or require a source contract incompatible with automated public ingestion.
- **Eval/repair signal**: `macro-calendar-core` omits one of the three BLS schedule events, BLS rows lack `source_url` or `reference_period`, event concepts enter numeric `MACRO_CORE_CONCEPTS`, or a deleted calendar/surprise page is restored instead of rendering overview catalysts.
- **Status**: [~]

### Task 35 — Detect Stale Event Bundle Series In Macro Status

- **File(s)**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 34
- **Touch set**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/integrations/macrodata/runner.py; src/parallax/app/surfaces/cli/commands/macro.py; tests/unit/test_cli_macro_commands.py`
- **Failing test first**: `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_event_bundle_series tests/unit/test_cli_macro_commands.py::test_macro_status_requires_importable_event_bundle_series -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Extend `macrodata_runtime_state` so status checks expected series membership per configured bundle, not only bundle names or numeric `macro-core` membership. Have `parallax macro status` pass all importable provider series plus per-bundle requirements for `macro-core`, `macro-calendar-core`, `treasury-auction-core`, and `fed-text-core`.
- **Verification**: `uv run pytest tests/unit/test_cli_macro_commands.py -q && uv run ruff check src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add a host-local macrodata fallback, do not mark stale packages usable merely because a bundle name exists, and do not require event series inside numeric `macro-core`.
- **On-demand context**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`
- **Kill/defer criteria**: macrodata-cli cannot expose bundle series lists from installed package metadata or imports.
- **Eval/repair signal**: `macro status` reports `required_bundles_available=true` and no missing bundle-series while installed `macro-calendar-core` lacks the BLS event series required by Parallax constants.
- **Status**: [~]

### Task 36 — Repin BLS Calendar Runtime And Verify Live Catalysts

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 34, Task 35
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/services/macro_module_views.py; tests/unit/domains/macro_intel/test_macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_show_bls_release_time_and_reference_period -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: In the external macrodata-cli checkout, bump the package to `0.1.12`, commit and push the BLS official-calendar implementation at Git rev `25ba5281d04a0ddc81ab6a07c4a5784b698100f9`, and repin Parallax to that versioned Git source. Keep runtime sync portable by using the packaged Git dependency, not a host-local checkout. Extend overview calendar catalyst descriptions to read source-provided `event_time_et` and `reference_period`, so BLS CPI, Employment Situation, and PPI catalysts show release time and reference period in the decision console.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_runtime.py tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q && uv run ruff check src tests`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_show_bls_release_time_and_reference_period -q`; `uv run parallax macro status`; `uv run parallax macro sync --bundle macro-calendar-core --start 2026-06-16 --end 2026-07-31`; direct repository/view-builder probe for BLS `event:*` facts, `macro_observation_series_rows`, and overview `event_catalysts`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add host-local macrodata fallback paths, do not mark stale packages usable, do not put BLS events in numeric `MACRO_CORE_CONCEPTS`, do not restore calendar/surprise pages, and do not fabricate actual/consensus/prior/revision values.
- **On-demand context**: external macrodata-cli `official_calendar` provider/catalog/bundle tests, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `tests/architecture/test_project_structure.py`
- **Kill/defer criteria**: macrodata-cli BLS branch cannot be published or pinned as a portable Git source, or live runtime cannot fetch official BLS schedule pages from the packaged dependency.
- **Eval/repair signal**: `macro status` reports missing BLS bundle series, `macro-calendar-core` live sync imports no BLS facts, BLS facts fail to project into `macro_observation_series_rows`, or overview catalysts omit BLS release time/reference period despite provenance carrying it.
- **Status**: [~]

### Task 37 — Add MOVE Rates-Volatility Proxy To Volatility Read

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 25, Task 36
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/_constants.py; src/parallax/domains/macro_intel/services/macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series tests/unit/test_catalog.py::test_catalog_documents_public_macro_terminal_proxies tests/unit/test_runtime.py::test_package_version_advances_for_move_proxy_release -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Add `yahoo:^MOVE` to macrodata-cli catalog and `volatility-core`, bump macrodata-cli to `0.1.13`, commit and push Git rev `1fde95d5b4ddff9bdec60cc9e1d25ec9027b10ce`, and repin Parallax to that packaged Git dependency. Map `yahoo:^MOVE` to `vol:move`, add it to retained `volatility/vix` chart/table evidence, and emit a backend MOVE diagnostics row from persisted history. Keep `vol:move` out of the global 126-point history gate so the new proxy improves the volatility module without making the whole macro snapshot partial during bootstrap.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py -q && uv run ruff check src tests`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`; live `uv run parallax macro sync --bundle macro-core --start 2026-06-01 --end 2026-06-16`; one-shot macro view projection; direct DB/module-view probe for `vol:move`.
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No restored volatility dashboard, no hidden gap or compatibility route, no frontend provider calls, no fake MOVE row, no claim that Yahoo `^MOVE` is an official licensed ICE feed, and no global snapshot downgrade while the proxy has short bootstrap history.
- **On-demand context**: external macrodata-cli catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Yahoo `^MOVE` disappears from public market data, or product requires official ICE/Bloomberg redistribution before displaying any rates-vol proxy.
- **Eval/repair signal**: `macro status` reports missing `yahoo:^MOVE`, `volatility/vix` has no MOVE row after `macro-core` sync, MOVE appears as a static UI row, or adding MOVE makes `latest_snapshot.status` partial solely because the proxy lacks 126 historical points.
- **Status**: [~]

### Task 38 — Add Treasury Auction Calendar Catalysts

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 17, Task 36
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/_constants.py; src/parallax/domains/macro_intel/services/macro_module_views.py; tests/unit/domains/macro_intel/test_macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_treasury_auction_provider.py::test_treasury_auction_latest_returns_next_nominal_auction_from_official_tentative_schedule tests/provider/test_treasury_auction_provider.py::test_treasury_auction_range_returns_nominal_auction_calendar_without_tips_rows tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_package_version_advances_for_treasury_auction_calendar_release -q`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_treasury_auction_calendar_event_concepts tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_prioritize_near_upcoming_treasury_auction_calendar -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: not delegated
- **Implementation**: Extend macrodata-cli `treasury_auction` with official Treasury tentative schedule XML events for next nominal 2Y/10Y/30Y auctions, keep completed auction result metrics in the same first-class `treasury-auction-core` event bundle, bump macrodata-cli to `0.1.14`, commit and push Git rev `a90da8c3f4c7139924043d9d496493ded4326d50`, and repin Parallax to that packaged dependency. Map the three new series to `event:treasury_auction_*_next` concepts, render them as `auction_calendar` overview catalysts with announcement/settlement/reopening details, and sort event catalysts by nearest upcoming calendar risk before truncating so Treasury supply events are not hidden behind source-order noise.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q && uv run ruff check src tests && uv run macrodata bundle fetch treasury-auction-core --asof 2026-06-16 --format json`; `uv run pytest tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`; `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py`; live `uv run parallax macro sync --bundle treasury-auction-core --start 2026-06-16 --end 2026-07-31`; direct DB/read-model/view probe for `event:treasury_auction_2y_next`, `event:treasury_auction_10y_next`, and `event:treasury_auction_30y_next`.
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Treasury sources; no unofficial auction calendar scraping, no restored `rates/auctions` route, no auction-tail calculation without when-issued yield, no host-local macrodata fallback, no compatibility aliases, and no event observations in numeric `MACRO_CORE_CONCEPTS`.
- **On-demand context**: external macrodata-cli `treasury_auction` provider/catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Treasury tentative schedule XML or FiscalData upcoming calendar source stops exposing stable public fields, or product requires auction-tail analysis before showing any supply calendar.
- **Eval/repair signal**: `macro status` reports missing `treasury_auction:*_next_auction_days`, live `treasury-auction-core` sync imports no upcoming auction facts, overview catalysts omit upcoming Treasury supply events despite projected rows, a deleted auction route is restored, or auction calendar events enter numeric macro scoring.
- **Status**: [~]

### Task 39 — Remove Frontend Unsupported Macro Route Shell

- **File(s)**: `web/src/features/macro/model/macroPageRegistry.ts`, `web/src/features/macro/model/macroRoutes.ts`, `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/MacroWorkbenchRoute.tsx`, `web/src/routes/macro.route.tsx`, `web/src/features/macro/ui/shell/macroShell.css`, `web/tests/unit/features/macro/model/macroRoutes.test.ts`, `web/tests/routes/macro.route.test.tsx`, `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: none
- **Touch set**: `web/src/features/macro/**`, `web/src/routes/macro.route.tsx`, `web/tests/unit/features/macro/model/macroRoutes.test.ts`, `web/tests/routes/macro.route.test.tsx`, `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `web/src/features/macro/**; web/src/routes/macro.route.tsx; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `tests/unit/features/macro/model/macroRoutes.test.ts::normalizes empty, nested, and correlation route tails`; `tests/routes/macro.route.test.tsx::hard-deletes unknown macro routes into the route error surface`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Remove frontend `unsupported` macro page/product-tier types, remove `wasUnknown` route metadata, make `parseMacroRouteTail` return `null` for unknown/deleted macro tails, make `web/src/routes/macro.route.tsx` throw the ordinary route error for those tails, and delete the macro-specific unsupported panel/CSS. The deleted macro URLs now behave like ordinary route errors rather than hidden, deferred, or compatibility macro pages.
- **Verification**: `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx --run && npm run typecheck && npm run lint && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not keep a macro-specific unsupported route shell, hidden product tier, deferred module state, direct-link compatibility branch, or dead CSS for deleted routes.
- **On-demand context**: `docs/FRONTEND.md`, `web/src/routes/router.tsx`, `web/src/features/macro/model/macroRoutes.ts`
- **Kill/defer criteria**: React Router route-error handling cannot display an ordinary 404 surface from the macro route component.
- **Eval/repair signal**: Deleted macro URLs render any macro module shell, macro module navigation, `unsupported` product-tier/type, or the text `不支持的宏观页面`.
- **Status**: [x]

### Task 40 — Hard Delete Rates Expectations And Redundant Liquidity Pages

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroRoutes.ts`, `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/MacroRatesSubnav.tsx`, `web/tests/fixtures/macroFixture.ts`, `web/tests/e2e/support/mockApi.ts`, `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts`, `web/tests/unit/features/macro/model/macroRoutes.test.ts`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/CONTRACTS.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: none
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/e2e/support/mockApi.ts`, `web/tests/e2e/golden-paths/macro-terminal.spec.ts`, `web/tests/e2e/golden-paths/macro-responsive-audit.spec.ts`, `web/tests/unit/features/macro/model/**`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/CONTRACTS.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules`; `web/tests/unit/features/macro/model/macroRoutes.test.ts::normalizes empty, nested, and correlation route tails`; `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts::rejects deleted rates expectations as a rates module`. Additional red checks for the redundancy cleanup: `liquidity/reserves`, `liquidity/transmission-chain`, and `liquidity/operations` still appeared in the backend catalog and frontend route parser before implementation; RRP/TGA did not yet include `liquidity:nyfed_rrp` or `liquidity:srf`; and the liquidity parent link still targeted transmission-chain.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Remove `rates/expectations` from the backend module allowlist, backend module config, related-route lists, route label maps, frontend module types, navigation tree, rates subnav, rates model guards, fixtures, mocked API, responsive audit route list, and Playwright hard-deleted route set. Delete fabricated FedWatch/CME meeting-probability fixture rows and policy-expectations chart/table labels rather than keeping a hidden or compatibility shell. The same cleanup removes redundant `liquidity/reserves`, generic `liquidity/transmission-chain`, generic `liquidity/operations`, and duplicate `liquidity/fed-balance-sheet` module ids, module configs, related-route links, frontend route types, navigation nodes, responsive audit routes, and chart/table labels while folding `liquidity:fed_assets`, `liquidity:reserve_balances`, `liquidity:nyfed_rrp`, and `liquidity:srf` into `liquidity/rrp-tga`, and moving the liquidity parent/default route to `liquidity/rrp-tga`.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run && npm run typecheck && npm run lint && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not retain a `rates/expectations`, `liquidity/reserves`, `liquidity/transmission-chain`, `liquidity/operations`, or `liquidity/fed-balance-sheet` module id, route descriptor, nav item, direct-link branch, fixture, fake FedWatch probability, policy-expectations chart/table id, fed-balance-sheet chart/table id, hidden unsupported shell, or backward-compatible alias. Future rate-probability work must rebuild the page from a legal source-backed CME/FedWatch or equivalent lane; future bank-reserves detail must stay folded into `liquidity/rrp-tga` until it gains distinct diagnostics and source scope; future liquidity-transmission/detail work must graduate through `liquidity/rrp-tga` or a new source-backed diagnostic page instead of a generic duplicate.
- **On-demand context**: `docs/FRONTEND.md`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: A legal meeting-probability source is approved and implemented in this same slice, making a source-backed route possible instead of a proxy page.
- **Eval/repair signal**: `rates/expectations`, `liquidity/reserves`, `liquidity/transmission-chain`, `liquidity/operations`, `liquidity/fed-balance-sheet`, fake `fed:next_meeting_*` concepts, `policy_expectations_*` ids, `fed_balance_sheet` chart/table ids, or `CME FedWatch` fixture text appear in runtime source, frontend fixtures, navigation, or supported module tests.
- **Status**: [x]

## 2026-06-17 Continuation Note — OKX/Deribit Crypto Derivatives

This continuation is recorded here instead of adding a new numbered task because the active SDD feature is already at its 40-task limit. The implementation adds source-backed macrodata-cli providers for OKX public data and Deribit public market data, adds `crypto-derivatives-core` with 14 BTC/ETH OI/funding/basis/DVOL series, wires providers into runtime, adds a first-class `bundle history crypto-derivatives-core` sync surface, and bumps/publishes the macrodata-cli checkout to `0.1.22` at Git rev `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`. In Parallax, it maps those series to `crypto_derivatives:*`, marks them optional for long-history readiness, adds the bundle to default `macro_sync.bundle_names`, updates CLI runtime diagnostics so the new bundle is not misclassified as `macro-core`, pins the packaged Git dependency, and folds the rows into retained `assets/crypto` table evidence plus crypto leverage diagnostics and missing-group data-health gaps for OI, funding, basis, and DVOL.

Verification and remaining runtime blocker are recorded in `verification.md`: local macrodata-cli and Parallax tests pass, Parallax runtime sees macrodata-cli `0.1.22` with all five configured bundles available, and the current restricted shell blocks external OKX/Deribit provider requests plus the configured Postgres host during live sync. `assets/crypto-derivatives` remains hard-deleted; no hidden route, page shell, compatibility alias, frontend provider call, fake options surface, GEX field, or normalized-history placeholder was added.

## 2026-06-17 Continuation Note — VIX Depth Source Health

This continuation is also recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `volatility/vix` as the only retained volatility surface and adds module data-health reference gaps for implemented but absent depth groups: VIX1D/VIX9D event premium, VVIX/SKEW tail depth, MOVE rates vol, and VIXY/VIXM futures-proxy pressure. A retained VIX/VIX3M-only page can still emit the volatility regime read, but it now reports `partial` with warning-level `module_reference` gaps instead of silently implying complete source coverage. `volatility/dashboard` remains hard-deleted; no hidden route, compatibility alias, CFE futures placeholder, options-surface row, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Credit Depth Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `credit/stress` as the only retained credit surface and adds module data-health reference gaps for implemented but absent depth groups: HYG/LQD ETF pressure, NFCI financial conditions, SLOOS bank lending, and FRED loan-quality evidence. A retained spread-only credit page can still emit the HY/IG/CCC regime read, but it now reports warning-level `module_reference` gaps instead of implying complete public credit coverage. `credit/cds` remains hard-deleted; no hidden route, compatibility alias, TRACE placeholder, ETF premium/discount row, licensed CDS proxy, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Policy Corridor Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `rates/fed-funds` as the retained policy-corridor surface and adds module data-health reference gaps for implemented but absent depth groups: DFF daily effective fed funds, SOFR 30D, OBFR unsecured funding, and EFFR/OBFR volume depth. A target/EFFR/IORB/SOFR-only page can still emit the corridor regime read, but it now reports warning-level `module_reference` gaps instead of implying complete policy-corridor coverage. Snapshot-missing module views now keep only the snapshot blocker and do not append source-depth reference gaps. `rates/expectations`, Fed text pages, auction pages, and `liquidity/subsurface` remain hard-deleted; no hidden route, compatibility alias, fake FedWatch probability, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Liquidity Depth Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `liquidity/rrp-tga` as the retained liquidity surface and adds module data-health reference gaps for implemented but absent depth groups: Fed assets/reserve balances, SOFR/IORB secured corridor, BGCR/TGCR repo depth, SOFR/BGCR/TGCR volume depth, and NY Fed RRP/SRF operations. An RRP/TGA-only page can still emit the liquidity regime read, but it now reports warning-level `module_reference` gaps instead of implying complete liquidity-source coverage. `liquidity/subsurface`, `liquidity/global-dollar`, duplicate balance-sheet routes, and generic liquidity operation routes remain hard-deleted; no hidden route, compatibility alias, OFR/STFM placeholder, cross-currency-basis row, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Economy Depth Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `economy/gdp`, `economy/employment`, and `economy/inflation` as the retained economy surfaces and adds module data-health reference gaps for implemented but absent depth groups: nominal GDP, GDPNow, industrial production/housing, consumption and consumer-buffer evidence; JOLTS openings, average hourly earnings, and labor participation; PCE/Core PCE, GDP deflator, market inflation expectations, and Michigan consumer expectations. Core-only economy pages can still emit their growth, labor, or inflation regime read, but now report warning-level `module_reference` gaps instead of implying complete economy-source coverage. `economy/consumer` and separate calendar/surprise pages remain hard-deleted; no hidden route, compatibility alias, actual/consensus/prior/revision placeholder, surprise row, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Rates Curve Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `rates/yield-curve` and `rates/real-rates` as retained rates surfaces and adds module data-health reference gaps for implemented but absent depth groups: 3M front-end, 5Y belly, 30Y long-end, TIPS real-rate decomposition, breakeven decomposition, full TIPS curve, breakeven curve, and 5Y5Y forward inflation. A 2Y/10Y-only curve page or 10Y-real-only real-rate page can still emit its rates regime read, but now reports warning-level `module_reference` gaps instead of implying complete rates-source coverage. `rates/auctions`, `rates/expectations`, deleted Fed text pages, and separate OIS/FedWatch placeholders remain hard-deleted or backlog-only; no hidden route, compatibility alias, fake meeting probability, OIS proxy, auction-tail row, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Asset Depth Source Health

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps `assets`, `assets/equities`, `assets/bonds`, `assets/commodities`, `assets/fx`, and `assets/crypto` as retained asset surfaces and adds module data-health reference gaps for implemented but absent depth groups: cross-asset breadth/duration/credit/volatility/commodity confirmation; equity growth leadership, small caps, global/sector proxies, and CFTC positioning; bond short/intermediate duration, TIP, credit beta, OAS spreads, and aggregate bond proxy; commodity Brent, NatGas, precious metals, copper, and ETF proxies; FX broad dollar, G10 pairs, Asia pairs, and FX ETFs; plus the existing OKX/Deribit crypto derivative groups. Core-only asset pages can still emit their market-board or asset-class regime read, but now report warning-level `module_reference` gaps instead of implying complete asset-source coverage. `assets/crypto-derivatives`, standalone CFTC/options/GEX pages, CDS proxy pages, commodity proxy shells, and ETF-flow placeholders remain hard-deleted or backlog-only; no hidden route, compatibility alias, options/GEX row, fake flow row, or static future-source backlog warning was restored.

## 2026-06-17 Continuation Note — Standalone Asset Correlation Route Hard Delete

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation keeps source-backed asset-correlation data inside the retained `assets` landing page but hard-deletes `/macro/assets/correlation` as a standalone product route. The cleanup removes the `matrix` page kind, route parser branch, navigation leaf, sidebar leaf, breadcrumb target, detail link, responsive-audit product route, `MacroMatrixPage`, `CorrelationRead`, standalone page tests, and unused correlation diagnostics UI/CSS. Backend module related routes no longer link to `/macro/assets/correlation`; `assets/correlation` is listed with other hard-deleted proxy-only paths in the module-catalog contract. The endpoint `/api/macro/assets/correlation` remains because it feeds the retained asset page's inline 60-day matrix and pair evidence, not a compatibility page.

## 2026-06-17 Continuation Note — Fed Communication Event Heatmap

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation folds official Fed text catalysts into the retained overview decision console's `event_heatmap` as policy-communication rows, preserving `source_url`, `document_type`, and speech `speaker` while keeping the same primary-source `event_catalysts` row. The old `14 天事件热力` product label is replaced with `事件热力` because the section now combines future 0-14 day official calendar/Treasury auction catalysts with recent Fed communication. Deleted Fed statement/speech pages remain deleted; no Fed text route, hidden compatibility shell, hawk/dove text score, React-side event scoring, or auction-result heatmap row was added.

## 2026-06-17 Continuation Note — Overview Liquidity Pressure

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation promotes retained `liquidity/rrp-tga` diagnostics into the overview decision console as a compact `liquidity_pressure` block with score, regime, summary, top source-backed drivers, implication, and invalidation. The frontend renders this as a first-screen `流动性压力` section between `确认 / 背离` and `交易映射`, matching the TimSun-style homepage read while leaving detailed liquidity rows on the retained RRP/TGA module. Deleted liquidity category aliases, transmission-chain, operations, reserves, global-dollar, and subsurface routes remain deleted; no hidden route, compatibility shell, React-side liquidity scoring, provider call, or static placeholder warning was added.

## 2026-06-17 Continuation Note — Overview Data Credibility Layer

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation promotes source-backed core feature provenance into the overview decision console as `data_credibility`, covering SPX, DXY, BTC, WTI, 10Y, VIX, HY OAS, and ON RRP when enough retained core rows exist. Each row carries the feature short label, display value, unit, observed date, source label, raw quality, and user-facing quality label; the block also reports an issue count. The frontend renders this as `数据可信度层`, keeps quality blockers inside the same section, and uses backend payload only for row quality/source/as-of display. Deleted or weak data-source pages remain deleted; no hidden route, compatibility shell, React-side provider call, frontend quality scoring, series-key leak, or static placeholder table was added.

## 2026-06-17 Continuation Note — Overview Judgement Review

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation promotes the existing Trade Map holding-period evidence into a first-screen `judgement_review` block, rendered as `昨日判断复盘` immediately after `交易映射`. The backend derives each row from all available Trade Map holding windows, currently 1D/5D/20D, and carries the expression label plus historical-trust summary; it removes the old top-level 1D horizon/status/P&L shape instead of keeping a compatibility payload. The frontend renders the backend windows only; it does not infer trade status, recompute P&L, call providers, or fabricate a previous-day LLM judgement. This adds the TimSun-style review loop without restoring deleted routes, adding hidden compatibility shells, or creating a new persistence table.

## 2026-06-17 Continuation Note — Overview Future 24/72h Catalysts

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation adds a TimSun-style `future_catalysts` block to the overview decision console, rendered as `未来 24/72h 催化剂` after `流动性压力` and before `交易映射`. The backend derives rows from explicitly windowed `scenario.watch_triggers` plus source-backed official calendar and Treasury auction calendar events inside the next three days, sorted by 24h/72h window and severity. Events outside 72h, auction-result rows, and Fed text documents remain in the existing event catalyst/heatmap lanes rather than being mixed into the short-window action list.

The frontend maps and renders backend fields only: label, description, 24h/72h window label, severity label, source label, and primary-source link when present. It does not compute event severity, scan providers, infer windows from dates, or add placeholder catalysts. Deleted calendar, auction, Fed text, and weak macro routes remain hard-deleted; no hidden route, compatibility shell, frontend provider call, React-side catalyst scoring, auction-tail placeholder, or actual/consensus/surprise row was added.

## 2026-06-17 Continuation Note — Overview Three Most Important Changes Evidence

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation upgrades the overview `top_changes` lane from generic signal cards to a TimSun-style `3 个最重要变化` block. Backend feature-delta changes now carry stable display fields for change, latest value, source, as-of date, severity, severity label, and a compact evidence label. The module view preserves those fields through `decision_console.top_changes`, and the frontend renders the backend evidence directly instead of parsing descriptions or inventing importance.

The ranking remains deterministic and backend-owned through existing scenario `top_changes` ordering and feature-delta fallback. The frontend does not rank changes, call providers, compute severity, or rebuild source/as-of labels from raw feature objects. Deleted macro routes and weak source pages remain hard-deleted; no hidden compatibility route, static placeholder source row, or React-side macro scoring was added.

## 2026-06-17 Continuation Note — Overview Watchlist Alerts

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation replaces the old overview `观察触发 / 失效条件` paired section with a TimSun-style `Watchlist 与触发提醒` block. Backend `_decision_console` now emits `watchlist_alerts` with assets from current Trade Map legs and rules from scenario watch triggers, scenario invalidations, and quality blockers. Each rule carries explicit kind, kind label, optional window, severity, and severity label so the frontend can render executable trigger rows without parsing raw evidence.

The frontend maps only the backend `decision_console.watchlist_alerts` payload into `watchlistAlerts`, renders that section after `事件催化`, and deletes the old decision-console `watchTriggers` / `invalidations` model fields instead of keeping a hidden compatibility path. The underlying `module_evidence.watch_triggers` and `module_evidence.invalidations` remain as raw evidence groups for other evidence presentations, but the first-screen decision console no longer duplicates them as a generic old section.

## 2026-06-17 Continuation Note — Overview Structured Analysis Chain

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation adds backend `module_read.structured_analysis` for the retained overview module, rendered as `跨域判断链` immediately after `今日决策台` and before the market board. The backend reuses existing deterministic domain diagnostics for assets, rates, Fed policy, liquidity, growth, employment, inflation, volatility, and credit, then compresses each available domain into regime, fact, evidence, trade implication, and invalidation rows. The frontend maps and renders only that backend payload through `MacroStructuredAnalysisPanel`; it does not compute cross-domain scores, inspect raw features, call providers, or keep a hidden compatibility section.

## 2026-06-17 Continuation Note — Overview Structured Market Thesis

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation adds a first `市场主线` row to backend `module_read.structured_analysis`, derived from the persisted scenario rather than frontend copy. The row uses the current regime label, base-case thesis/trade/invalidation when present, top-change evidence, and current Trade Map expression; if base-case fields are absent it falls back to the same deterministic scenario invalidations and Trade Map labels already used elsewhere. The structured-analysis row cap is widened so adding the market thesis does not squeeze out credit or volatility when all retained domains have diagnostics. No new route, provider call, LLM summary, compatibility field, or frontend scoring path was added.

## 2026-06-17 Continuation Note — Overview Fed Communication Structured Row

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation adds a source-backed `美联储沟通` row to backend `module_read.structured_analysis` when official Fed text catalysts are present. The row reuses the same `fed_text` event-catalyst candidate already used by `event_catalysts` and `event_heatmap`, exposing document type, source, speaker, document title/date, Fed communication watch text, trade implication, and invalidation. This makes Fed communications part of the first-screen structured analysis without restoring deleted Fed statement/speech pages, adding hawk/dove scoring, calling providers from the frontend, or keeping a compatibility route.

## 2026-06-17 Continuation Note — Overview Structured Analysis No Domain Drop

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation removes the hard 10-row truncation from backend `module_read.structured_analysis`. After adding `市场主线` and optional `美联储沟通`, a fully populated snapshot can produce 11 rows: market thesis, Fed communication, assets, rates, policy, liquidity, growth, employment, inflation, volatility, and credit. The regression test now proves all retained keys survive together, so better data coverage cannot accidentally hide the last domain. No frontend compatibility path, route change, or hidden overflow bucket was added.

## 2026-06-17 Continuation Note — Overview Structured Analysis Frontend No Domain Drop

This continuation is recorded without adding a new numbered task because the active SDD feature is at its 40-task limit. The implementation removes the remaining frontend model-side `structured_analysis` 8-row cap so the overview UI consumes every retained backend row in order: market thesis, Fed communication, assets, rates, policy, liquidity, growth, employment, inflation, volatility, and credit. The overview fixture now represents the complete retained domain chain, and the component test asserts policy, growth, employment, inflation, volatility, and credit render together on the page. No hidden overflow UI, compatibility field, route change, or frontend domain scoring was added.

## 2026-06-17 Continuation Note — Overview Market Event Flow Hard Cut

This continuation supersedes the earlier overview `event_catalysts` and `event_heatmap` decision-console slices. The implementation removes `decision_console.event_catalysts` and `decision_console.event_heatmap` from the backend module-view payload, removes their frontend model fields and rendering sections, and adds sibling `module_read.market_event_flow` rendered as `市场事件流` after `跨域判断链` and before `跨域市场板`. The event stream carries source-backed official calendar, Treasury auction calendar/result, and Fed text rows with category, impact, window, severity, watch text, and primary-source URL when present.

The hard cut keeps `decision_console.future_catalysts` only for executable 24h/72h items. Broader events are not hidden below the fold, not duplicated inside the decision console, and not preserved behind compatibility aliases. Deleted calendar, auction, Fed text, surprise, and proxy routes remain deleted; no hidden section, React-side event scoring, provider call, old field fallback, or backwards-compatible event component was retained.

## 2026-06-17 Continuation Note — Overview News Event Flow

This continuation extends the retained `module_read.market_event_flow` stream with projected News Intel rows. `/api/macro/modules/overview` now reads the same `news_page_rows` projection used by `/api/news` through `NewsPageQuery`, passes bounded recent rows into `build_macro_module_view(...)`, and maps each news row into a source-backed `kind=news` market-event row with headline, summary, source domain, canonical URL, market-scope category, asset tags, severity, and `改变主线 / 观察主线 / 不改主线` impact label from the projected signal decision class.

The implementation deliberately does not read raw `news_items`, run provider calls from the macro API, add frontend joins to `/api/news`, restore deleted event/news routes, or reintroduce `decision_console.event_catalysts` / `decision_console.event_heatmap`. News events are part of the sibling `市场事件流` only, after `跨域判断链` and before `跨域市场板`, matching the TimSun-style event-flow lane without duplicating first-screen decision-console actions.

## 2026-06-17 Continuation Note — Actionable Data Health Gaps

This continuation makes the retained macro diagnostics panels preserve backend `data_health` gap structure instead of flattening missing-source rows into one-line chips. `buildMacroDataHealthBuckets(...)` now returns structured gap items with key, label, severity, scope, and remediation detail, and the overview, leaf, asset, and rates diagnostics panels render those records as repair-oriented lists. This keeps source-health gaps actionable: operators can see what is missing and what repair action is expected, such as historical backfill, bundle sync, or projection rebuild.

The cleanup removes the old macro health chip classes and rendering paths rather than keeping a compatibility display. Frontend code still does not infer providers, invent remediation copy, call macrodata/news providers, or show static backlog rows for deleted pages. Backend `remediation_hint` remains the source of repair copy, while future/institutional source backlog stays in SDD/tech-debt docs until implemented.

## 2026-06-17 Continuation Note — Source-Gated TimSun Gap Map

This continuation adds `docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` as the
source-gated backlog for the remaining TimSun parity work. The reference first
separates the current macrodata-cli bundle baseline from true missing source
coverage, then classifies the remaining gaps as implemented, public candidate,
license gate, model gap, or no-source. It identifies the next public-source
candidates as OFR STFM funding depth, Cboe CFE VX/VXT futures depth, and BLS/BEA
actual/revision lanes, while keeping CME FedWatch, OPRA/options/GEX, broader
cross-currency basis, CDS/CDX, and consensus-surprise work behind explicit
operator approval.

No runtime page, module id, route alias, frontend fixture, static future-source
row, or compatibility shell was added. The tech-debt row now points to the
source-gated matrix instead of carrying an undifferentiated gap list.

## 2026-06-17 Continuation Note — Economic Calendar Surprise Hard Cut

This continuation removes the last misleading surprise semantics from retained
official BLS/BEA calendar rows. Backend `market_event_flow` now classifies
official economic-data calendars as `release_revision` / `实际/修正` and tells
operators to track official actual values, prior revisions, and methodology
changes. It no longer emits `data_surprise`, `数据波动`, or market-expectation
gap language for those rows because Parallax does not yet have a timestamped
consensus source.

No calendar/surprise route, hidden compatibility alias, fake consensus field,
actual/prior/revision placeholder, frontend provider call, or React-side event
scoring was added. Consensus surprise remains source-gated in
`docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md`.

## 2026-06-17 Continuation Note — Auction Calendar Future-Source Copy Hard Cut

This continuation removes runtime and fixture copy that described future auction
or source integrations as if they were product capabilities. Backend
`market_event_flow` Treasury auction calendar rows now watch only source-backed
auction demand, announcement size, and settlement-date funding pressure; they no
longer mention `auction tail 未接入` because Parallax does not have a legal
when-issued yield lane or tested tail formula. The overview fixture also drops
the stale `未来宏观日历待接入` future-integration gap, and the macro workbench
diagnostics no longer says `来源待接入` when provenance rows are absent. A later
Source Detail hard cut replaced the interim absent-source copy with the numeric
fact `0 个来源`.

This is a hard cleanup, not an offline switch: no hidden future-source row,
compatibility field, placeholder route, fake auction-tail metric, React-side
source inference, or static "待接入" status label remains in the retained macro
frontend/runtime scope. Auction tail stays source-gated in
`docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` until an approved WI source and
formula test exist.

## 2026-06-17 Continuation Note — Future Integration Contract Hard Delete

This continuation removes the remaining `future_integration_gaps` data-health
contract instead of keeping it as an always-empty compatibility bucket. Backend
module views now return only `module_gaps`, `chart_gaps`, and `global_gaps`;
generic module evidence no longer derives watch triggers from future-source
backlog rows; and `MacroModuleConfig` no longer has the all-empty `gap_codes`
slot. Frontend contracts, fixtures, rates/page view-model aggregation, and
diagnostic panels no longer declare, populate, aggregate, or label a
`未来集成` scope.

This keeps retained pages focused on actionable source health: implemented but
missing data stays in `module_gaps` / `global_gaps`, while unimplemented or
licensed TimSun parity work stays only in source-gated documentation. No hidden
future-source bucket, static backlog field, compatibility fallback, or empty UI
section remains in the retained macro runtime/frontend contract.

## 2026-06-17 Continuation Note — Data Gap Placeholder Hard Cut

This continuation removes the remaining frontend `数据缺口待确认` placeholder
from macro data-health presentation. `gapLabel(...)` now turns code-only gap
payloads into display-ready labels such as `历史样本不足：60d` and `基差缺失`,
so a retained page can still show an actionable repair row even when a backend
payload lacks a human label. Completely unlabeled and uncoded gap objects are
filtered out instead of rendered as product copy.

This is another subtraction pass: no frontend inference of providers, no static
source backlog row, and no compatibility wording was added. Backend-provided
labels and remediation hints remain preferred; code-derived labels are only the
last-resort display path for real gap codes.

## 2026-06-17 Continuation Note — Decision Console Metadata Placeholder Hard Cut

This continuation removes decision-console placeholder copy for missing
scenario probability, trade-map time window, confirmation signals, invalidation
signals, unknown signal codes, and unknown trade expressions. The frontend now
renders scenario meta, trade windows, `确认：...`, and `失效：...` only when the
model contains source-backed display text. The model returns `null` for missing
or unmapped signal arrays instead of manufacturing `待确认` strings, prefers
backend trade-map labels, and drops unknown English trade expressions that lack
a display label.

This is a hard cleanup, not an offline switch: no hidden fallback label,
compatibility alias, old payload field, React-side code-to-copy inference, or
generic "待确认" product text remains in the retained decision-console path.
Known backend signal codes still map to their explicit Chinese labels, and
Chinese display text supplied by the backend remains displayable.

## 2026-06-17 Continuation Note — Backend Signal Placeholder Hard Cut

This continuation removes the backend source of `待确认信号` and
`待确认交易映射` from macro scenario and module-view payload generation. The
scenario engine now drops unmapped trigger codes from display summaries unless
they carry an explicit display label or known mapping. The module-view builder
filters unmapped overview evidence, top changes, future catalysts, watchlist
rules, structured-analysis signal lines, and unknown Trade Map expressions
instead of manufacturing generic labels. Judgement Review rows also require a
real Trade Map label before they render.

This keeps the API display-ready rather than relying on the frontend to hide
bad copy. Known product codes such as `global_term_premium` are explicitly
whitelisted with real Chinese labels; unknown English codes remain raw
developer identifiers only if they are non-display contract fields, and they no
longer become user-facing text.

## 2026-06-17 Continuation Note — Backend Diagnostics Pending Status Hard Cut

This continuation removes generic `待确认` status labels from the retained macro
module-view backend. Single-point asset, FX, liquidity-volume, net-liquidity,
volatility ETF, and volatility spread rows now report
`insufficient_history` / `样本不足` when the current observation exists but the
change window required for a directional judgement is unavailable. Structured
analysis rows also fall back to `样本不足` when no regime label is available,
and Judgement Review windows map missing status metadata to the same explicit
sample-shortfall state.

This keeps the API display-ready and honest: current values can remain visible,
but Parallax no longer presents missing history as a vague decision state. No
frontend hiding path, compatibility label, or generic pending status was added.

## 2026-06-17 Continuation Note — Backend Gap Payload Label Derivation Hard Cut

This continuation removes the remaining backend `数据缺口：待补齐数据源`
fallback from macro gap payload generation. Known retained gap codes now map to
specific labels such as `MOVE 指数缺失`, `VIX 期限结构缺失`, `Fed 日历缺失`,
`SLOOS 缺失`, and `平均时薪缺失`. Unknown real gap codes derive a readable
code-based label instead of collapsing into a generic backlog sentence.

This is a product cleanup, not a hidden compatibility shim: no static source
backlog row, future-source route, legacy field, or generic data-source
placeholder remains in backend macro gap payloads. Implemented source gaps keep
their concrete missing-source label until the matching observations are present.

## 2026-06-17 Continuation Note — Asset Overview Pending Placeholder Hard Cut

This continuation removes the last frontend `待确认` placeholders from the
retained asset overview path. `buildAssetMarketGroups(...)` now returns `null`
for missing row as-of and row quality/source metadata instead of manufacturing a
display label. The asset board renders missing dates as `缺少日期`, omits absent
source-quality chips, and the page-level `截至` stat renders only when the
snapshot supplies a real as-of value. Daily-brief coverage and gap-count metrics
show `样本不足` when the backend quality payload lacks a numeric value; the old
fake `0` gap count was removed too.

No hidden downline path, old placeholder branch, or frontend provider inference
was added. The retained asset page still shows current rows and explicit data
health diagnostics, but it no longer presents missing metadata as a pending
confirmation state.

## 2026-06-17 Continuation Note — Rates Corridor Missing Indicator Copy Hard Cut

This continuation removes the remaining rates corridor runtime `待补齐：...`
copy from the retained rates UI. `RatesCorridorChart` still renders the missing
SOFR 30D line when the backend/model says the corridor data is partial, but the
label is now `缺少指标：SOFR 30D`, which describes the current data gap rather
than promising a future integration.

No chart line, missing-label payload, route, CSS bucket, compatibility branch,
or fallback data source was added or hidden. The rates page remains honest about
missing corridor evidence while dropping future-backlog product copy from the
operator surface.

## 2026-06-17 Continuation Note — Macro Fixture Pending Confirmation Copy Hard Cut

This continuation removes `PCE 尚待确认` from the macro fixture/mock product
surface. The inflation mock page still shows a PCE-related contradiction, but it
now labels it as `PCE 发布窗口` with explicit BEA-release validation context
instead of a generic pending-confirmation phrase.

This keeps tests, mock API responses, and browser QA fixtures aligned with the
runtime cleanup rule: missing or future evidence should be displayed as a
current source/event condition, not as vague `待确认` product copy. No production
fallback, hidden branch, or compatibility fixture was added.

## 2026-06-17 Continuation Note — Frontend Unlabeled Gap Sentinel Hard Cut

This continuation removes the frontend `未标注数据缺口` sentinel from retained
macro data-health mapping. `gapLabel(...)` now returns `null` for gap payloads
that lack a display label, title, or known code mapping, and
`buildMacroDataHealthBuckets(...)` drops those payloads directly instead of
manufacturing a placeholder label and filtering it later.

The overview fixture data-health row also now reports `全局历史样本不足` with a
concrete remediation hint instead of `部分全局历史待回填`. This keeps mock API,
component tests, and runtime view-model semantics aligned: unknown gaps are not
displayed, and known partial history is described as a current sample-shortfall
state. No hidden fallback label, compatibility branch, or future-backlog product
copy remains in this path.

## 2026-06-17 Continuation Note — Frontend Module Read Summary Status Fallback Hard Cut

This continuation removes the frontend path that used `snapshot.status` or
`snapshot.status_label` as module brief copy when backend `module_read` lacked a
headline, summary, or regime label. `macroReadSummary(...)` now returns `null`
for missing read fields, `buildMacroWorkbenchBrief(...)` carries that absence
through the model, and missing read copy is no longer replaced with snapshot
status text.

The asset daily-brief side rail accepts a nullable fallback, but it no longer
uses status metadata as judgement copy. This keeps status metadata in panel meta
where it belongs and prevents `部分可用`, `partial`, or `暂无` from masquerading
as a TimSun-style macro judgement. No legacy field, hidden compatibility branch,
or frontend scoring inference was added.

## 2026-06-17 Continuation Note — Asset Judgement Empty Panel Hard Cut

This continuation removes the asset overview `今日判断` side section when both
the backend `daily_brief` payload and backend module-read summary are absent.
`MacroAssetOverviewPage` now mounts the section only when there is real
judgement content, and `AssetDailyBrief` returns `null` rather than
manufacturing `缺少今日判断`.

This is a deletion of a no-content panel, not a hidden offline state: the page
keeps core asset prices, cross-asset diagnostics, data diagnostics, and
correlation evidence visible. Missing judgement belongs in data-health/source
diagnostics or backend repair work, not in an empty product card.

## 2026-06-17 Continuation Note — Module Brief Empty Panel Hard Cut

This continuation removes the top-level `宏观简报` / `模块简报` panels when the
backend module read supplies neither summary text nor display rows. The new
`hasMacroWorkbenchBrief(...)` model helper treats status/as-of metadata as panel
chrome, not content; `MacroOverviewModulePage` and `MacroLeafModulePage` mount
`MacroInsightBrief` only when this helper says there is real brief content.
`MacroInsightBrief` also returns `null` for empty brief models as a defensive
component boundary.

This completes the same hard-deletion pattern used for the asset judgement
panel: no empty card, no `缺少模块解读` placeholder, no use of
`snapshot.status_label` as user-facing judgement, and no hidden compatibility
branch. Retained market evidence, decision console, diagnostics, and data
health sections continue to render.

## 2026-06-17 Continuation Note — Decision Console Empty Section Hard Cut

This continuation removes empty subsection shells from the retained `今日决策台`.
When backend read payloads only provide evidence confirmations/contradictions,
the decision console now renders that real signal and drops empty sections for
top changes, trade mapping, two-week scenarios, and data credibility instead of
printing `暂无关键变化`, `暂无交易映射`, `暂无情景计划`, or `暂无阻断缺口`.

This keeps the TimSun-style operator surface dense and evidence-first: a section
exists only when the backend supplies usable decision content. No CSS hiding,
placeholder copy, or compatibility branch was added.

## 2026-06-17 Continuation Note — Driver Board Empty Panel Hard Cut

This continuation removes the `传导链` / `驱动与反证` board when both backend
transmission nodes and evidence groups are absent. The new
`hasMacroWorkbenchDrivers(...)` helper treats only real transmission rows or
evidence items as board content; overview and leaf pages mount
`MacroDriverBoard` only when that helper passes.

`MacroDriverBoard` also now drops empty child sections defensively. A module with
only evidence does not render an empty transmission lane, a module with only
transmission does not render an empty evidence lane, and a module with neither
does not print `暂无` or `暂无可用证据`. Missing drivers remain visible through
data-health/source diagnostics rather than an empty decision panel.

## 2026-06-17 Continuation Note — Data Gap Empty Detail Hard Cut

This continuation keeps `数据诊断` as the source/data-quality surface but removes
empty gap-detail chrome. `MacroDiagnosticsPanel` now renders `缺口明细` only when
at least one gap bucket has real items or a leaf page has a nonzero global
reference count. Empty buckets are filtered out instead of displaying `暂无`.

The asset overview diagnostics rail now follows the same rule: the summary still
shows `缺口 0`, but the side rail no longer prints `暂无数据缺口` when there is no
gap payload to inspect. This preserves the audit signal while deleting empty
detail UI.

## 2026-06-17 Continuation Note — Source Detail Empty State Hard Cut

This continuation removes empty source-detail drawers from macro diagnostics.
`buildMacroWorkbenchDiagnostics(...)` now reports zero provenance as
`0 个来源` instead of `暂无来源`, keeping the source count as a numeric fact.

`MacroDiagnosticsPanel` and `AssetDiagnosticsBoard` now render the source table
only when provenance rows exist. When source count is zero, the summary still
shows the zero count, but no closed drawer or `暂无数据源元信息` table state is
inserted into the page.

## 2026-06-17 Continuation Note — Rates Empty Fact And Diagnostics Hard Cut

This continuation applies the same deletion rule to the rates workbench. Empty
rates fact strips now return `null`; a fact row renders source, date, and status
metadata only when those fields exist, so `暂无来源`, `暂无日期`, and `暂无状态`
are not manufactured.

Rates diagnostics now filter out empty health buckets and render source
diagnostics only when provenance rows exist. A rates module with no gap payloads
and no source rows keeps the panel-level data status, but does not insert
`暂无`, `来源状态`, or `暂无数据源元信息` filler sections.

## 2026-06-17 Continuation Note — Rates Decision Support Empty Group Hard Cut

This continuation removes empty evidence groups from rates `决策支持`. The panel
now returns `null` when confirmations, contradictions, watch triggers, and
invalidations are all empty. When an evidence item has a label but no
description, the label remains visible and the missing detail is omitted instead
of rendered as `暂无`.

This keeps rates decision support aligned with the broader hard-cut rule: no
empty groups, no placeholder detail rows, and no compatibility copy.

## 2026-06-17 Continuation Note — Missing As-Of Date Hard Cut

This continuation removes the last product-level `暂无日期` fallback from macro
page state. `macroAsOfLabel(...)` now returns `null` when the snapshot does not
carry an as-of label or date. Freshness alerts omit the date prefix in that case
instead of leading with placeholder copy.

Route headers and the rates read panel now render `截至` only when a real as-of
date exists. Missing snapshot dates stay absent; they are not converted into a
header metric, panel meta suffix, or rates state row.

## 2026-06-17 Continuation Note — Source Gap Priority Tightening

This continuation updates `docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` with
a first-principles implementation order for remaining TimSun parity sources. The
new priority gate ranks candidates by public access, retained-page impact,
macrodata/macro-sync fit, and deterministic fact/model ownership.

The next public-source lanes are now explicit: OFR STFM for liquidity depth,
BLS/BEA actual and revision lanes for economy pages, Cboe CFE futures history
for volatility depth, internal Trade Map judgement history, and deterministic
Fed text delta scoring. CME FedWatch, OPRA/GEX, TRACE/CDS/CDX, broad
cross-currency basis, and consensus surprise stay license/model-gated with no
runtime route, static fixture, or hidden compatibility surface.

## 2026-06-17 Continuation Note — Runtime No-Resurrection Architecture Guard

This continuation hardens the deletion decision with an architecture test rather
than another manual grep. `tests/architecture/test_macro_no_compatibility_contract.py`
now scans macro runtime/frontend source for deleted product route paths, removed
standalone page components, and source-backlog placeholders such as FedWatch,
OPRA, TRACE, CDS/CDX, Cboe DataShop/LiveVol, auction-tail, when-issued, or STFM
runtime copy.

The only allowed remaining `assets/correlation` runtime reference is the
correlation data endpoint/query used by the retained asset landing page. It is
not a restored `/macro/assets/correlation` product route. This keeps the cleanup
enforced as a no-compatibility contract: deleted routes cannot come back as
hidden shells, unsupported pages, static future-source rows, or convenience
aliases.

## 2026-06-17 Continuation Note — Source Table Primitive Empty State Hard Cut

This continuation deletes the last `MacroSourceTable`-owned empty source panel.
The table primitive now returns `null` when `source.rows` has no valid rows
instead of rendering `暂无数据源元信息`.

This keeps the component contract aligned with the page-level hard cuts: source
tables are evidence views, not empty-state generators. Legacy one-object source
metadata is not inferred into rows, no raw provider/status/run id leaks into the
UI, and callers with zero provenance keep the summary count only.

## 2026-06-17 Continuation Note — Rates Detail Empty Panel Hard Cut

This continuation removes the `利率明细` panel when no primary rates detail
table has rows. `RatesDetailTables` now returns `null` for empty primary table
sets instead of rendering a `0 张` panel with `暂无利率明细`.

This keeps the rates workbench consistent with the fact strip, decision support,
and diagnostics hard cuts: detail tables are evidence surfaces, not empty
layout placeholders. Normal rates pages with real primary tables still render
the panel in the same order.

## 2026-06-17 Continuation Note — Rates Primary Chart Empty Panel Hard Cut

This continuation removes the rates page-level `利率主图` panel when the backend
primary chart has no series seed. `RatesPrimaryVisual` still calls its hooks in a
stable order, but returns `null` before rendering chart chrome when
`primary_chart.series` is empty.

The low-level chart primitives keep their accessible empty states for direct
component use and tests. The rates product page no longer turns an absent
primary chart into a visible `暂无可绘制走廊数据` card.

## 2026-06-17 Continuation Note — Leaf Market Evidence Empty Panel Hard Cut

This continuation removes the generic leaf `主市场证据` panel when both evidence
channels are empty: the backend primary chart has no series seed and all
supporting tables have zero rows. `MacroMarketBoard` now returns `null` in that
case instead of rendering a panel whose only content is chart primitive empty
copy such as `暂无可绘制序列`.

The rule is evidence-preserving rather than cosmetic: a market board still
renders when either chart seed data or table rows exist. Leaf diagnostics and
data-health panels remain visible so missing evidence is reported through the
repair surfaces, not through an empty market card.

## 2026-06-17 Continuation Note — Asset Market Empty Surface Hard Cut

This continuation removes the asset landing `核心资产行情` surface when the
retained asset table has no displayable rows. `buildAssetMarketGroups(...)` now
keeps only asset groups with rows, and `MacroAssetOverviewPage` mounts the
surface only when the aggregate asset row count is positive.

This deletes the `项目 0` / empty-group behavior and prevents `暂无...快照`
rows from becoming product content. Cross-asset diagnostics, data-health, and
correlation surfaces remain available so missing asset rows are still handled by
repair and diagnostic paths.

## 2026-06-17 Continuation Note — Asset Correlation Empty Surface Hard Cut

This continuation tightens the retained asset landing page's inline `60日相关性`
support read. The standalone `/macro/assets/correlation` page remains deleted,
and the retained inline surface now mounts only while loading/erroring or when
the backend returns at least one available positive or negative correlation
pair.

Empty successful responses no longer render the `60日相关性` section, a one-sided
successful response renders only the populated `正相关` or `负相关` group, and
the visible error state uses its own `暂不可用` meta instead of no-data copy.
This deletes the `暂无相关性样本`, empty pair group, and `暂无` support copy from
the product path instead of hiding it behind CSS or keeping a compatibility
shell.

## 2026-06-17 Continuation Note — Asset Availability Empty Coverage Hard Cut

This continuation removes the asset diagnostics `覆盖` drawer when the backend
`availability_proxy_notes` table has no usable coverage rows. A coverage row now
needs a real item label plus at least one real status, latest observation,
history coverage, or note field before it becomes product content.

Missing optional coverage cells render as absent table cells instead of `暂无`,
and rows whose item label is itself placeholder copy are dropped. This keeps the
asset data-health rail focused on inspectable data-quality evidence rather than
empty coverage chrome or placeholder cell values.

## 2026-06-17 Continuation Note — Asset Market Row Placeholder Hard Cut

This continuation removes row-level placeholder content from the retained asset
market dashboard. `buildAssetMarketGroups(...)` now drops asset rows that lack a
real display name, symbol, or latest value, while keeping optional
delta/date/source fields absent instead of manufacturing `暂无` or `缺少日期`.

`AssetMarketDashboard` also no longer carries a group-level empty-row branch or
a primitive-level empty paragraph; the asset page already mounts the market
surface only when at least one displayable row exists. This keeps asset market
tables as price evidence, not missing-price placeholders.

## 2026-06-17 Continuation Note — Source Row Placeholder Hard Cut

This continuation removes row-level placeholder content from
`MacroSourceTable`. Source diagnostics now require a real provider label plus at
least one audit fact before a row is rendered, and unknown internal provider ids
are dropped instead of being converted into a generic `数据源` row.

The component also no longer routes source metadata through the generic
`MacroDataTable`, because that primitive fills sparse cells with `暂无`.
`MacroSourceTable` now renders only columns that have real values across the
kept rows, so absent score/notes/count fields do not become product content or a
compatibility layer.

## 2026-06-17 Continuation Note — Generic Metric And Evidence Placeholder Hard Cut

This continuation removes placeholder metric cards and evidence items from the
generic macro module presentation model. `buildMacroMetrics(...)` now requires a
real metric label plus a real value before emitting a tile, and no longer falls
back to `未命名指标` or a formatted `暂无` value.

`buildMacroEvidenceGroups(...)` now requires both a real evidence label and a
real detail before emitting an item. Label-only evidence rows are not treated as
product evidence, so downstream overview/leaf driver boards cannot manufacture
`暂无` detail copy from sparse backend payloads.

## 2026-06-17 Continuation Note — Decision Console Sparse Item Hard Cut

This continuation removes sparse decision-console items before they reach the
overview workbench panels. Confirmation/contradiction evidence, top changes,
quality blockers, and watchlist rules now require a real detail string in
addition to a real label or code-derived label.

The cut happens in `buildMacroDecisionConsole(...)`, so downstream panels cannot
accidentally render label-only items as `暂无` detail rows. This keeps the
decision console focused on inspectable changes, blockers, and triggers rather
than placeholders derived from partial payloads.

## 2026-06-17 Continuation Note — Chart Series Placeholder Hard Cut

This continuation removes unlabeled chart content from the macro chart model.
Generic time-series and normalized-return series now require a real backend
label, short label, or title before they enter the model; otherwise the series
is dropped instead of becoming `未命名指标` in legends or chart status copy.

Correlation heatmap rows follow the same rule: canonical concept keys without a
display label no longer become matrix rows or columns. Yield-curve points keep
their semantic tenor fallback, such as `10Y`, because those labels are derived
from known Treasury tenor concepts rather than generic placeholder copy.

## 2026-06-17 Continuation Note — Generic Table Placeholder Hard Cut

This continuation removes generic `MacroDataTable` placeholder cells from macro
product tables. `formatMacroTableValue(...)` now returns `null` for missing,
empty, arbitrary-object, or literal `暂无` values instead of turning them into
display text.

`buildMacroTableModel(...)` now drops empty cells, rows with no displayable
cells, and columns with no displayable cells. `MacroDataTable` renders missing
cells as absent content rather than `暂无`, while explicit backend statuses such
as `缺失` remain visible because they are real source-provided values.

## 2026-06-17 Continuation Note — Nullable Scalar Formatter Hard Cut

This continuation removes the shared `formatMacroScalar(...)` placeholder
contract. The formatter now returns `null` for missing, empty, arbitrary-object,
empty-array, or literal `暂无` inputs instead of manufacturing generic display
copy.

Callers now have to prove a scalar exists before emitting product content:
module brief rows, structured analysis rows, liquidity pressure details, event
flow rows, future catalysts, rates facts, transmission nodes, and table source
notes all drop sparse values rather than rendering `暂无` or empty DOM shells.

## 2026-06-17 Continuation Note — Market Board Empty Chart Hard Cut

This continuation removes page-level empty chart chrome from `MacroMarketBoard`.
The board now treats chart evidence as drawable chart-model output, not raw
`chart.series.length`, before deciding whether the primary visual should mount.

When a market board has usable table evidence but no drawable chart points, it
keeps the table and omits the empty chart region entirely. Chart primitives keep
their accessible empty states for direct component use, but the product market
board no longer surfaces `暂无可绘制序列` as content.

## 2026-06-17 Continuation Note — Rates Corridor Empty Primary Visual Hard Cut

This continuation applies the same page-level evidence rule to the Fed funds
rates primary visual. The rates workbench no longer treats any non-empty raw
chart series as enough reason to mount the `利率主图` panel.

For `rates/fed-funds`, the primary visual now requires a recognized Fed funds
corridor concept before it fetches series data, and it requires at least one
drawable corridor series after model filtering before the panel remains on the
page. Unknown proxy series and empty corridor models therefore delete the chart
panel instead of rendering a loading shell or `暂无可绘制走廊数据`.

`RatesCorridorChart` also no longer owns an internal empty-state fallback: an
empty corridor model returns `null`. This keeps the component from becoming a
future compatibility path that can reintroduce empty chart chrome through a new
caller.

## 2026-06-17 Continuation Note — Generic Table Empty State Hard Cut

This continuation removes `MacroDataTable` as a generic empty/loading-state
surface. Production callers already mount tables only after page-level evidence
gates prove there are displayable rows, so the table primitive should not
manufacture product content from an empty model.

`MacroDataTable` now returns `null` when `buildMacroTableModel(...)` has no
displayable rows. The unused `state` prop, `TableState` helper, `暂无表格行`,
`表格加载中`, and dead `.macro-table-state-panel` CSS were deleted rather than
kept as hidden compatibility code.

## 2026-06-17 Continuation Note — Generic Chart Empty State Hard Cut

This continuation removes the generic chart primitive empty states that turned
no drawable data into product chrome. `MacroTimeSeriesChart` now returns `null`
when there are no drawable series and no explicit backend status label, while
still preserving source-backed status messages such as insufficient history or
minimum-point requirements.

`MacroYieldCurveChart` and `MacroHeatmap` also return `null` when their models
have no drawable points or rows. The generic `暂无可绘制序列`,
`暂无收益率曲线数据`, and `暂无相关性矩阵数据` branches were deleted so empty
chart primitives cannot reappear as compatibility surfaces through new callers.

## 2026-06-17 Continuation Note — Correlation Empty Surface Hard Cut

This continuation removes the remaining correlation primitive empty surfaces.
`MacroCorrelationMatrixTable` now returns `null` when there are no drawable
assets or matrix rows, and `MacroCorrelationPairList` returns `null` when there
are no correlation pairs.

The `emptyLabel` prop, `暂无可用资产`, `暂无可用配对`, and dead
`.macro-correlation-empty` CSS were deleted. Asset correlation pages already
mount the surface only when loading, error, or real pair evidence exists, so
primitive-level no-data copy was only a compatibility path.

## 2026-06-17 Continuation Note — Supporting Table Empty Shell Hard Cut

This continuation removes the last `primarySupportingTable` compatibility shell.
When a macro module has no backend table, the helper now returns `null` instead
of manufacturing a `${module_id}_supporting_table` object with `status:
"missing"`.

The unused `emptyTable` and `emptyChart` factories were deleted. Overview, leaf,
and asset pages now pass only real backend tables into market/asset surfaces; no
table means no table-derived product chrome rather than a hidden or downlined
placeholder.

## 2026-06-17 Continuation Note — Backend Unnamed Indicator Hard Cut

This continuation removes the backend `未命名指标` fallback from macro runtime
payload builders. Supported macro concepts already have complete public
metadata, so an unlabeled concept is now treated as a projection contract error
instead of being converted into anonymous product copy.

`macro_series_view` and `macro_module_views` now require a public concept label
from feature or concept metadata. `macro_gap_payloads` keeps known missing
concept gaps as `缺少当前数据：{label}`, but unmapped missing codes degrade to an
explicit `数据质量缺口：{public_code}` repair item rather than manufacturing an
indicator name. A macro architecture guard now prevents the placeholder from
returning to runtime source.

## 2026-06-17 Continuation Note — Backend Empty Chart Factory Hard Cut

This continuation removes the backend `_empty_chart()` compatibility factory.
All retained macro modules now have an explicit primary chart spec, and that
catalog invariant is tested directly.

`build_macro_module_view(...)` and the missing-snapshot payload path now require
`config.chart_specs[0]` instead of falling back to an `id: None` chart object.
If a future module has no chart spec, that is a catalog contract failure to fix
at the source rather than a product surface to pad with empty chart chrome.

## 2026-06-17 Continuation Note — Frontend Unknown Identifier Hard Cut

This continuation removes the frontend `unknown_chart` and `unknown_table`
identifier fallbacks from macro presentation models. Missing chart/table ids are
now treated as invalid payload contracts that produce no chart/table model or
caption, rather than synthetic identifiers that keep UI chrome alive.

`macroModulePageModel` now returns `null` for invalid chart/table ids and
captions. `macroChartModel` and `macroTableColumns` return empty models when the
backend id is missing. Macro market, rates, and asset diagnostics callers now
skip the affected block instead of wrapping it in a generic caption. The macro
architecture guard also blocks `unknown_chart` and `unknown_table` from runtime
source.

## 2026-06-17 Continuation Note — Backend Generic Metadata Fallback Hard Cut

This continuation removes the backend `单位未标注`, `宏观图表`, and `宏观表格`
fallbacks. These strings made incomplete metadata look like valid product copy,
which is the wrong failure mode for a decision console.

Feature unit labels now require either feature-level or concept metadata
`unit_label`; missing unit metadata raises a projection contract error. Chart
and table titles now require explicit mappings for every retained catalog spec.
The macro architecture guard blocks those generic fallback strings from runtime
source.

## 2026-06-17 Continuation Note — Backend Provider Label Fallback Hard Cut

This continuation removes the backend `未知来源` provider fallback. Missing
observation rows may omit a source label, but any non-empty provider name must
resolve through explicit public provider metadata.

The provider label map now includes the retained macro provider aliases that
current module views actually consume (`ny_fed`, `treasury`, `okx`, and
`deribit`). Test-only `fixture` source names were removed from module view
fixtures instead of being added back as compatibility metadata. Unregistered
non-empty provider names now raise `Missing macro provider label metadata`.

## 2026-06-17 Continuation Note — Unknown Status/Regime Fallback Hard Cut

This continuation removes generic `未知`, `未知状态`, and `未知宏观状态`
fallbacks from macro runtime source. Backend status, quality, and regime
translation now treats unmapped non-empty codes as projection contract errors,
rather than rendering unknown labels into the decision console.

The retained regime aliases produced by current scenario and module paths now
have explicit labels, including `risk_on`, `risk_off_confirmation`,
`low_quality_stress`, and `corridor_drain`. API contract fixtures were updated
to provide explicit `data_quality: ok` instead of relying on missing-field
defaults. Frontend scalar/table/source formatters now drop `unknown` and
unmapped source statuses instead of manufacturing placeholder copy or retaining
empty source metadata tables.

## 2026-06-17 Continuation Note — Decision Console Quality Blocker Hard Cut

This continuation removes the backend quality-blocker `数据缺口` label fallback.
Decision-console quality blockers now require an explicit `label` or `code` from
scenario/data-health inputs; unlabeled blockers raise
`Missing macro quality blocker label metadata` instead of becoming generic
repair items.

The normal data-health-derived quality blocker path already supplies code,
label, description/remediation, and severity. This cut only rejects scenario
payloads that cannot tell the operator which provider, concept, or contract
needs repair.

## 2026-06-17 Continuation Note — Signal Diagnostics Heading Fallback Hard Cut

This continuation removes frontend signal-diagnostics fallback headings from
`macroWorkbenchModel`. Growth, employment, inflation, liquidity, credit,
volatility, asset, and asset-class diagnostics now require backend `label`
metadata before rendering.

`MacroSignalDiagnosticsPanel` derives its accessible region label from the
diagnostics model itself. Module pages no longer pass fixed labels such as
`波动率诊断` or `资产分项诊断`; a missing backend label deletes the diagnostics
surface instead of letting frontend copy keep it alive.

## 2026-06-17 Continuation Note — Signal Diagnostics Synthetic Row Key Hard Cut

This continuation removes frontend synthetic row ids from signal diagnostics.
Diagnostics rows now require a backend `key`; rows missing that key are dropped
instead of being kept alive with ids like `volatility_diagnostics:0`.

The same stricter row contract applies to growth, employment, inflation,
liquidity, credit, volatility, asset, and asset-class diagnostics, plus
liquidity-pressure driver formatting because it reuses the liquidity diagnostic
row parser.

## 2026-06-17 Continuation Note — Market Event Flow Identity Hard Cut

This continuation removes frontend identity and title fallbacks from macro
market event flow. `buildMacroMarketEventFlow(...)` now requires backend
`market_event_flow.key` and `market_event_flow.label`; missing either deletes
the event-flow surface instead of manufacturing `market_event_flow` /
`市场事件流`.

Event rows now require backend `key` metadata as well. Rows without keys are
dropped instead of being retained with synthetic ids such as `market-event:0`.

## 2026-06-17 Continuation Note — Decision Console Top/Quality Key Hard Cut

This continuation removes frontend synthetic keys from decision-console
`top_changes` and `quality_blockers`. These rows now require backend `code`
metadata before rendering; code-less rows are dropped instead of receiving
synthetic keys like `top:0` or `quality:0`.

This keeps the operator console aligned with backend repair contracts: every
visible top change or blocker must identify the exact scenario signal or data
quality contract it came from.

## 2026-06-17 Continuation Note — Decision Console Evidence/Credibility Identity Hard Cut

This continuation removes additional frontend decision-console identity
fallbacks. Confirmations, contradictions, future catalysts, judgement-review
rows, and data-credibility rows now require backend identity before rendering;
rows without `code`, `key`, or `concept_key` are dropped instead of receiving
synthetic ids such as `confirm:0`, `contradict:0`, `future-catalyst:0`,
`judgement-review:0`, or `data-credibility:0`.

Judgement-review and data-credibility sections also require backend `key` and
`label` metadata. `MacroDecisionConsolePanel` no longer renders an orphan
quality-blocker section under a frontend `数据可信度层` fallback when the backend
omits `data_credibility`.

## 2026-06-17 Continuation Note — Trade Map/Watchlist/Structured Identity Hard Cut

This continuation removes the remaining frontend synthetic identities from the
macro decision console and structured-analysis chain. Scenario cases now
require backend `case`; Trade Map rows require backend `expression`; watchlist
sections require backend `key` and `label`; watchlist assets require backend
`key`; watchlist rules require backend `key` or `code`; structured-analysis
sections require backend `key` and `label`; structured-analysis rows require
backend `key`.

Rows missing those identity fields are dropped instead of being retained with
ids such as `scenario:0`, `trade:0`, `watchlist-asset:0`,
`watchlist-rule:0`, or `structured-analysis:0`.

## 2026-06-17 Continuation Note — Decision Console Generic Copy Fallback Hard Cut

This continuation removes another layer of frontend product-copy fallbacks from
the decision console. Liquidity-pressure blocks now require backend `key` and
`label`; Trade Map historical-review and portfolio-review sections require
backend labels; unmapped checklist kinds, section kinds, severity codes, and
event kinds no longer render generic labels such as `行动`, `宏观`, `提示`, or
`事件`.

Missing or unmapped metadata now removes that row or meta fragment instead of
making an incomplete backend payload look like an intentional operator-facing
decision block.

## 2026-06-17 Continuation Note — Backend Decision Console Contract Hard Cut

This continuation moves the same subtraction back into the macro module-view
projection contract. Overview `liquidity_pressure` now carries the stable
backend key required by the frontend model; the module-view builder no longer
defaults missing quality-blocker severity to `warning`, unknown top-change
sections to raw section codes, unknown watchlist severity to `关注`, or unknown
liquidity-pressure regimes to neutral `5.0/10`. Top-change rows must also carry
explicit section metadata instead of falling back to `macro`. Data-gap mappings
likewise must carry explicit `code`, `label`, and `severity`; mapped gap objects
no longer receive implicit `warning` severity or generic remediation copy in
source availability tables.

Malformed backend projection metadata now raises explicit contract errors at
`macro_module_view_v3` build time instead of shipping operator-facing fallback
copy that looks intentional.

## 2026-06-17 Continuation Note — Concept Metadata Raw Fallback Hard Cut

This continuation removes backend module-view fallbacks that exposed raw macro
`concept_key` or observation units as product copy. Observation-derived
features, availability/source rows, missing-concept evidence, event labels, and
feature label/short/unit helpers now require explicit concept metadata for
`label`, `short_label`, and `unit_label` instead of falling back to strings such
as `rates:dgs5` or raw units such as `percent`.

The macro no-compatibility architecture guard now rejects the retired raw
concept metadata fallback expressions so future changes cannot silently
reintroduce them.

## 2026-06-17 Continuation Note — Frontend Model Identity Hard Cut

This continuation removes frontend model-layer synthetic identities from macro
metrics, data-health gaps, table rows, and asset-correlation labels. Metrics now
require backend `concept_key`; data-health gaps require backend `code`; semantic
table rows require backend `row_id` and no longer append row indexes; unknown
correlation assets are omitted instead of being displayed as `资产`.

The frontend macro model architecture guard now rejects the deleted synthetic
identity templates (`metric:${index}`, `${bucketKey}:${index}`,
`${stable}:${rowIndex}`, `row:${index}` / `row:${rowIndex}`) and the retired
correlation asset label fallback.

Remaining follow-up from the scan: rates diagnostics still contain
index-derived keys/labels such as `policy-row:${index}`, `curve-row:${index}`,
and `政策读数 ${index + 1}`. Those belong to the next hard-cut slice rather than
this generic table/metric/correlation cleanup.

## 2026-06-17 Continuation Note — Rates Diagnostics Row Identity Hard Cut

This continuation removes the rates workbench diagnostics fallbacks called out
by the previous scan. Policy diagnostics, curve diagnostics, curve history
series, curve tenor comparisons, and real-rate diagnostics now require backend
`key` and `label` metadata before rendering. Curve history points also require
`observed_at`; their stable keys now use `seriesKey:observed_at` instead of
point indexes.

The frontend macro model architecture guard now rejects the retired rates
diagnostic templates such as `policy-row:${index}`, `curve-row:${index}`,
`curve-history:${seriesIndex}`, `tenor:${index}`, `${groupKey}:${index}`,
`政策读数 ${index + 1}`, `曲线 ${index + 1}`, `利差历史 ${seriesIndex + 1}`,
`期限 ${index + 1}`, `实际利率读数 ${index + 1}`, and `点 ${pointIndex + 1}`.

## 2026-06-17 Continuation Note — Rates Facts Raw Concept Hard Cut

This continuation removes the remaining rates fact/raw concept fallback. Rates
facts now require backend `concept_key` and `label`; a known concept no longer
supplies a missing fact label, and missing concept keys no longer receive
`fact:${index}`. `humanizeRatesConceptKey(...)` now returns labels only for
explicit concept metadata and returns `null` for unknown concept ids instead of
splitting raw names such as `rates:not_mapped` into display copy.

Rates explanatory copy still scrubs known concept ids to approved labels, but
unknown concept ids are removed rather than shown as raw ids or generated words.
The frontend macro model architecture guard rejects `fact:${index}` and raw
`conceptKey.split(":")` humanization.

## 2026-06-17 Continuation Note — Rates Gap Summary Hard Cut

This continuation removes the rates workbench gap-summary compatibility path.
Rates data-health summaries now require backend `code` plus explicit
`label`/`display_value`; gaps missing either side are dropped instead of
receiving `gap:${index}` or generated labels from raw codes.

`humanizeGapCode(...)` and its raw `code.split(/[:_]+/)` display fallback were
deleted from the rates model. The frontend macro model architecture guard now
rejects both retired patterns.

## 2026-06-17 Continuation Note — Provenance Source Row Contract Hard Cut

This continuation removes source-table identity and provider-label inference.
Backend macro provenance rows now emit explicit `row_id` and `source_label`
fields and no longer publish a generic `source` display field. Frontend
`MacroSourceTable` requires both fields before rendering a row and no longer
builds row ids with `${source}:${index}` or infers provider labels from
`label`/`source`/`name`.

Rates source metadata summaries now read `source_label`, keeping the rates page
on the same contract. The frontend macro model architecture guard rejects the
retired source-row identity and source-label fallback expressions.

## 2026-06-17 Continuation Note — Chart Status And Placeholder Hard Cut

This continuation removes chart-level placeholder contracts from the macro
market board and chart models. Chart status now remains `null` when the backend
does not provide status metadata; the frontend no longer manufactures
`unknown`. Chart ids are required before a chart can render, and yield-curve /
time-series models no longer assign `unknown_chart`.

Unlabeled chart series and heatmap rows are dropped instead of receiving
placeholder labels such as `未命名指标`, and market-board table blocks require an
explicit caption before rendering. The frontend macro model architecture guard
now rejects the retired chart status fallback expressions.

## 2026-06-17 Continuation Note — Asset Overview Placeholder Hard Cut

This continuation removes asset-overview placeholder data from the daily brief,
asset market rows, and diagnostics gap lists. Daily briefs now require backend
`headline` and `status`; daily-brief blocks require explicit `stance`, and
daily-brief quality summaries require explicit `status`. Missing fields no
longer become `今日判断暂不可用`, `unknown`, or `neutral`.

Asset market rows no longer derive symbols by splitting row ids such as
`asset:dji`; symbols must come from backend table cells or raw symbol/ticker
fields. Asset, workbench, and rates diagnostics gap list items no longer emit
`data-severity="unknown"` when severity is absent. The frontend macro model
architecture guard rejects all retired asset-overview placeholder expressions.

## 2026-06-17 Continuation Note — Page Gap Raw-Code Label Hard Cut

This continuation removes the shared page-view gap-code display generator.
`gapLabel(...)` now returns only backend display-ready text
(`display_value`/`label`/`title`) and no longer turns raw strings or `code`
values into labels such as `历史样本不足：60d` or `基差缺失`.

Freshness alerts may still use structured gap `code` values to decide whether a
module is stale, but alert item labels require explicit backend copy. The
frontend macro model architecture guard rejects the retired `gapCodeLabel(...)`,
`GAP_CODE_TERMS`, raw code splitting, and generic stale item fallback copy.

## 2026-06-17 Continuation Note — Diagnostics Status Summary Hard Cut

This continuation removes status-summary fallbacks that made incomplete
diagnostics look healthy or display-ready. Workbench brief status now uses the
shared status-label contract instead of raw snapshot `status`; workbench
diagnostics status uses only backend `summary_label` and no longer exposes raw
`summary_status`.

The diagnostics panel no longer displays `正常` when status metadata is absent.
The asset overview diagnostics header omits the status badge unless
`summary_label` exists, and rates diagnostics no longer manufactures source
state text from source row counts when `sourceMeta` is absent. The frontend macro
model architecture guard rejects the retired raw-status and source-count
fallback expressions.

## 2026-06-17 Continuation Note — Chart/Table Caption Hard Cut

This continuation removes frontend caption generation for module charts and
tables. `chartCaption(...)` and `tableCaption(...)` now require backend `title`
metadata; valid ids alone no longer produce display text.

The static `TITLE_BY_ID` map, id-splitting `labelFromIdentifier(...)`, and
`WORD_LABELS` caption dictionary were deleted. The frontend macro model
architecture guard rejects those retired caption fallback paths.

## 2026-06-17 Continuation Note — Driver Board Identity Hard Cut

This continuation removes synthetic identity and copy from the macro driver
board. Transmission nodes now require explicit backend `key`, `label`, and
`value`; the UI no longer falls back to `kind`, `status_label`, `status`, or
row index.

Evidence groups now carry item `key` from backend `code`/`key`, and evidence
items without identity are dropped before rendering. The driver board no longer
builds list keys from labels plus indexes. Macro fixtures were updated with
explicit evidence and transmission identity to match the stricter contract, and
the frontend macro model architecture guard rejects the retired driver fallback
expressions.

## 2026-06-17 Continuation Note — Detail Table Identity Hard Cut

This continuation removes the remaining table-list index identity fallbacks from
macro market boards and rates detail/diagnostic tables. Supporting and detail
tables must now have backend `id`, backend `title`, and rows before they can
participate in a rendered table stack.

`MacroMarketBoard`, `RatesDetailTables`, and `RatesDiagnosticsPanel` no longer
use `String(table.id ?? index)` and no longer leave empty panels when the only
tables are missing backend display identity. The frontend macro model
architecture guard rejects the retired table-index key fallback.

## 2026-06-17 Continuation Note — Chart Series Status And Yield Label Hard Cut

This continuation removes the remaining chart-model health and yield-label
fallbacks. Time-series model rows now keep `status` as `null` when neither the
chart series nor hydrated series payload provides explicit status metadata;
they no longer manufacture `ok` for renderable series.

Yield-curve points now require backend labels. The chart model no longer derives
labels such as `10Y` from tenor metadata when the backend omits display copy.
The frontend macro model architecture guard rejects both retired fallback
expressions.

## 2026-06-17 Continuation Note — Rates Diagnostics Label Hard Cut

This continuation removes default rates diagnostics section labels. Policy,
yield-curve, and real-rate diagnostics now require backend `label` metadata
before they can produce a diagnostics block; the frontend no longer inserts
`政策走廊诊断`, `曲线诊断`, or `实际利率诊断` when the backend omits the label.

The rates diagnostics builders still preserve backend-provided labels and
regime/shape suffixes, but missing top-level labels now remove the block instead
of creating product copy locally. The frontend macro model architecture guard
rejects the retired default-label expressions.

## 2026-06-17 Continuation Note — Rates Market Headline Hard Cut

This continuation removes the rates-market headline fallback that combined
module titles with readiness labels. The rates workbench now uses only backend
`module_read.headline` for the market-read headline; when the backend omits it,
the market-read section is not rendered.

The rates model no longer creates strings such as `政策利率走廊：部分可用`, and
the rates UI no longer keeps an empty `利率简报` region alive for missing backend
headline copy. The frontend macro model architecture guard rejects the retired
headline fallback expression.

## 2026-06-17 Continuation Note — Rates Market Explanation Dead Field Hard Cut

This continuation deletes the unused rates workbench `marketExplanation` field
instead of keeping a hidden or nullable compatibility path. The field was no
longer rendered by the rates UI and only survived as model-generated copy plus
unit-test text aggregation.

The rates model no longer generates neutral explanatory text from module ids or
backend note fallbacks for this dead field. The frontend macro model
architecture guard rejects both `neutralFallbackExplanation(...)` and
`marketExplanation` in macro source files.

## 2026-06-17 Continuation Note — Asset Daily Brief Fallback Hard Cut

This continuation removes the asset landing `daily_brief` compatibility
fallback. The asset `今日判断` panel now renders only when the backend provides a
valid normalized `daily_brief`; `module_read.summary` no longer substitutes for
that product surface.

`AssetDailyBrief` no longer accepts a `fallback` prop, and
`MacroAssetOverviewPage` no longer computes `readSummary` for the asset judgment
rail. The default macro asset fixture now declares explicit `symbol` column/cell
metadata so the route-level asset page still proves the core market surface with
real display identity instead of weakening the test.

## 2026-06-17 Continuation Note — Correlation Matrix Caption Hard Cut

This continuation removes frontend-generated correlation matrix captions.
`MacroCorrelationMatrixTable` now requires an explicit `label` from its caller;
when the caption is absent the matrix chrome is not rendered.

The matrix component no longer creates labels from `data.window`, so missing
backend/caller display copy cannot appear as a polished `60d 资产相关性矩阵`
surface. The frontend macro model architecture guard rejects the retired
caption fallback expression.

## 2026-06-17 Continuation Note — Driver Board Meta Fallback Hard Cut

This continuation removes the driver-board panel meta fallback. `MacroDriverBoard`
now displays only explicit caller-provided `meta`; it no longer creates strings
such as `0 条证据` from the evidence count.

Overview and leaf macro pages already pass deliberate route/module meta, while
standalone or future reuse without meta now shows no panel meta instead of
manufacturing a summary. The frontend macro model architecture guard rejects the
retired evidence-count meta fallback.

## 2026-06-17 Continuation Note — Asset Row As-Of Fallback Hard Cut

This continuation removes module-snapshot date backfill from asset market rows.
`buildAssetMarketGroups(...)` now derives row `asOf` only from row/table data
such as `observed_at`, `latest_observed_at`, `date`, or `asof_date`; it no
longer accepts a page-level fallback date.

The asset landing page still shows module-level snapshot metadata in the page
header, but missing row-level dates remain blank rather than inheriting that
module date. The frontend macro model architecture guard rejects the retired
`fallbackAsOf` path.

## 2026-06-17 Continuation Note — Source Degradation Note Hard Cut

This continuation removes generic source-row degradation note copy. Macro source
tables now display backend `notes`, `message`, or mapped public source labels
only; internal degradation codes are dropped instead of being rewritten as
`存在降级原因`.

This keeps provenance rows honest: if the backend cannot provide a user-facing
reason, the notes column disappears instead of implying a known explanation. The
frontend macro model architecture guard rejects the retired generic degradation
copy and two-argument `displayText(...)` fallback.

## 2026-06-17 Continuation Note — Rates Corridor Missing Concept Hard Cut

This continuation removes raw concept-id exposure from the fed-funds corridor
chart model. Corridor missing labels are now emitted only for known
`CORRIDOR_SERIES_BY_CONCEPT` mappings; unknown missing concept keys are dropped.

The rates corridor model still reports known missing lines such as `SOFR 30D`,
but it no longer surfaces internal ids such as `fed:not_mapped`. The frontend
macro model architecture guard rejects the retired `?? concept` fallback.
