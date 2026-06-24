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
- **Review result**: parent-reviewed
- **Implementation**: Add tests before changing the catalog. Assert retained ids match the allowlist, deleted ids are absent, and retained `related_routes` never point to deleted ids.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests must not introduce hidden/deferred route tiers or direct-link compatibility expectations.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Kill/defer criteria**: Existing module catalog API cannot delete weak ids without a broader contract decision.
- **Eval/repair signal**: Test failure indicates a retained route still links to a deleted route or a deleted route remains registered.
- **Status**: [x]

### Task 3 — Delete Weak Macro Module Catalog Entries

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Owner**: parent agent
- **Depends on**: Task 2
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- **Conflict set**: `web/src/features/macro/model/macroNavigationTree.ts; src/parallax/app/surfaces/api/routes_macro.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Remove proxy-only module ids/configs and strip them from all related-route lists. Do not add route tier metadata, hidden support, deferred module state, or compatibility aliases.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Retained module ids remain stable; deleted module ids behave the same as unknown ids.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Deleted modules are still referenced by a required current UI test after Task 2 has been updated.
- **Eval/repair signal**: Existing route tests fail because frontend descriptors still expect deleted labels.
- **Status**: [x]

### Task 4 — Add Decision Console Unit Tests

- **File(s)**: `tests/unit/domains/macro_intel/test_macro_scenario_engine.py`, `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/test_macro_scenario_engine.py`, `tests/unit/domains/macro_intel/test_macro_regime_engine.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py; src/parallax/domains/macro_intel/services/macro_regime_engine.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add fixture observations for rates, liquidity, volatility, credit, and assets; assert top changes, confirmations, contradictions, invalidations, watch triggers, trade map, two-week scenario cases, and data blockers are present and human-readable.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: No LLM calls; no wall-clock-sensitive assertions except injected `computed_at_ms`.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Kill/defer criteria**: Existing scenario output already contains all needed fields and only API/frontend shaping is required.
- **Eval/repair signal**: Raw gap codes or empty labels appear in expected user-facing fields.
- **Status**: [x]

### Task 5 — Implement Decision Console Fields

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Owner**: parent agent
- **Depends on**: Task 4
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`, `src/parallax/domains/macro_intel/services/macro_regime_engine.py`
- **Conflict set**: `src/parallax/app/surfaces/api/routes_macro.py; web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add deterministic decision-console shaping from existing features, chain, panels, triggers, and gaps. Add one current nested section for new fields and do not keep duplicate compatibility field names. The 2026-06-17 continuation adds `scenario_cases` for base/upside/downside two-week trade planning with probability, thesis, trade, entry, stop, and invalidation.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No new worker, no new table, no frontend scoring.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Required fields cannot be derived from current persisted snapshot without changing storage shape.
- **Eval/repair signal**: Snapshot payload hash or publication tests fail unexpectedly.
- **Status**: [x]

### Task 6 — Add API Deleted-Route Tests

- **File(s)**: `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 5
- **Touch set**: `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`
- **Conflict set**: `src/parallax/app/surfaces/api/routes_macro.py; src/parallax/domains/macro_intel/services/macro_module_views.py; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add tests using existing repository/session fixtures. Assert `/api/macro` exposes decision-console data, including current scenario-case planning when present, and deleted module ids use the ordinary not-found path with no deferred/compatibility payload.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: API tests read fixture snapshots, not runtime DB.
- **On-demand context**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Kill/defer criteria**: There is no existing route fixture and adding one would exceed this feature.
- **Eval/repair signal**: API response omits decision-console fields or renders deleted pages as legacy modules.
- **Status**: [x]

### Task 7 — Implement API And Module View Hard Deletion

- **File(s)**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Owner**: parent agent
- **Depends on**: Task 6
- **Touch set**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`
- **Conflict set**: `web/src/features/macro/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Surface decision-console data from persisted snapshots and remove any module-view branches for deleted ids. Deleted ids must not return a special unavailable/deferred payload.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: API must not call macrodata or external providers.
- **On-demand context**: `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Contract change requires generated OpenAPI updates outside current task.
- **Eval/repair signal**: Frontend typecheck fails because generated/handwritten contract types need updates.
- **Status**: [x]

### Task 8 — Add Frontend Navigation And Overview Tests

- **File(s)**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`
- **Owner**: parent agent
- **Depends on**: Task 7
- **Touch set**: `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/tests/routes/macro.route.test.tsx`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts`
- **Conflict set**: `web/src/features/macro/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `tests/routes/macro.route.test.tsx::removed macro routes are not registered`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add tests for reduced navigation, overview decision-console order, two-week scenario-case rendering, deleted URLs and bare category aliases not registered, and absence of raw gap codes.
- **Verification**: `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx tests/unit/features/macro/model/macroPageRegistry.test.ts --run`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests use fixtures and MSW; no live HTTP; tests must not expect hidden/deferred route rendering.
- **On-demand context**: `docs/FRONTEND.md`, `web/tests/fixtures/macroFixture.ts`
- **Kill/defer criteria**: Existing fixture types cannot represent decision-console data without contract update.
- **Eval/repair signal**: Test snapshots show raw internal codes, duplicate sections, or deleted route descriptors.
- **Status**: [x]

### Task 9 — Implement Frontend Hard Deletion And Decision Console

- **File(s)**: `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/model/macroPageRegistry.ts`, `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`, `web/src/features/macro/ui/pages/macroPages.css`
- **Owner**: parent agent
- **Depends on**: Task 8
- **Touch set**: `web/src/features/macro/model/macroNavigationTree.ts`, `web/src/features/macro/model/macroPageRegistry.ts`, `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`, `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`, `web/src/features/macro/ui/pages/macroPages.css`
- **Conflict set**: `web/src/shared/**; web/src/styles/**; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `tests/routes/macro.route.test.tsx::removed macro routes are not registered`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Delete weak route descriptors, bare category redirect aliases, and hidden-label preservation; render overview as a decision console, including backend-supplied two-week scenario cases; and remove deleted-route rendering branches. Keep CSS macro-owned and under harness limits.
- **Verification**: `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx tests/unit/features/macro/model/macroPageRegistry.test.ts --run`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No route module or presentational component may call `useQuery`, `getApi`, or `postApi` directly.
- **On-demand context**: `docs/FRONTEND.md`
- **Kill/defer criteria**: UI cannot fit mobile without larger shell changes.
- **Eval/repair signal**: CSS architecture harness fails, mobile route smoke shows overlap, or deleted routes still appear in registry output.
- **Status**: [x]

### Task 10 — Add macrodata Diagnostics Tests

- **File(s)**: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`, `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- **Owner**: parent agent
- **Depends on**: Task 1
- **Touch set**: `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`, `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata tests; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_rates_core_bundle_exposes_missing_api_key_diagnostics tests/unit/test_bundles.py::test_rates_core_bundle_marks_all_series_missing_unavailable tests/cli/test_bundle_commands.py::test_rates_core_without_fred_api_key_uses_public_csv tests/cli/test_bundle_commands.py::test_rates_core_all_series_failing_is_unavailable -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: In the external macrodata-cli repo, add mocked tests for FRED API-key mode, public CSV fallback mode, public CSV timeout diagnostics, and provider-level bundle coverage summaries.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q`
- **Review owner**: parent agent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Tests do not call live FRED, Yahoo, NY Fed, Treasury, or CFTC.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`
- **Kill/defer criteria**: Existing result envelope cannot accept diagnostics without a model change in macrodata-cli.
- **Eval/repair signal**: Bundle coverage loses available non-FRED observations when FRED fails.
- **Status**: [x]

### Task 11 — Implement macrodata FRED And Bundle Diagnostics

- **File(s)**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/errors.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Owner**: parent agent
- **Depends on**: Task 10
- **Touch set**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/errors.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata implementation; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_rates_core_bundle_exposes_missing_api_key_diagnostics tests/cli/test_bundle_commands.py::test_rates_core_all_series_failing_is_unavailable -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add redacted `access_mode` details to FRED successes and errors; add `source_health` to bundle snapshots with provider requested/available/missing/status/error-code/retryability summaries. Do not keep duplicate legacy diagnostics fields.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/unit/test_bundles.py tests/provider/test_fred_provider.py tests/cli/test_bundle_commands.py -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not print API keys or environment variable values.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`
- **Kill/defer criteria**: Diagnostics require a breaking macrodata-cli result-envelope change that cannot be consumed in this feature.
- **Eval/repair signal**: `macrodata bundle macro-core` becomes slower or less available than baseline.
- **Status**: [x]

### Task 12 — Documentation And Source Backlog

- **File(s)**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 5, Task 7, Task 9, Task 11, Task 14
- **Touch set**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DEBT.md`
- **Conflict set**: `AGENTS.md; CLAUDE.md; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Document hard-deleted macro surfaces, decision-console contract, macrodata diagnostics, and the source backlog that remains after this feature. Update external macrodata-cli docs in its repo when diagnostics are implemented.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent agent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: SDD feature directory contains only spec, plan, tasks, and verification.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/DESIGN_DISCIPLINE.md`
- **Kill/defer criteria**: Implementation is split into successor SDD records before docs can truthfully describe shipped behavior.
- **Eval/repair signal**: SDD validator reports unexpected artifacts, false verification, or active task-board size issues.
- **Status**: [x]

### Task 13 — Final Verification And Browser QA

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 12
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `src/**; web/src/**; coordinate with macrodata-cli for external macrodata verification; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/architecture/test_completion_gates.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Run repository gates, macrodata-cli gates, and browser QA for `/macro` plus retained primary child routes across desktop/mobile. Record command outputs and manual UI evidence.
- **Verification**: `make check-all`
- **Review owner**: parent agent
- **Factory lane**: Final integration
- **Deterministic constraints**: Do not claim completion unless all tasks are `[x]`, `make check-all` exits 0, required DoD lanes have no gate-disqualifying skips, and verification records full evidence. Opt-in `live` diagnostics remain outside normal CI per `docs/TESTING.md`.
- **On-demand context**: `docs/FRONTEND.md`, `docs/TESTING.md`, `docs/WORKFLOW.md`
- **Kill/defer criteria**: `make check-all` fails for unrelated baseline issues that the user chooses not to address in this feature.
- **Eval/repair signal**: Browser QA finds overlap, blank charts, raw codes, or deleted route reachability failures.
- **Status**: [x]

### Task 14 — Add macrodata Official Calendar Bundle

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 10, Task 11
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata provider/bundle changes; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_runtime.py::test_runtime_wires_official_calendar_provider tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add a new `official_calendar` provider for Federal Reserve FOMC calendar HTML and BEA release-date JSON. Add a separate default `macro-calendar-core` bundle containing reachable FOMC, GDP, and PCE next-event series. Task 34 extends the same bundle with BLS CPI, Employment Situation, and PPI official schedule pages. Use event date as `observed_at`, `days_until` as value, and source/time/title metadata in provenance. Do not add these series to `macro-core`.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check .`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official public Fed/BEA/BLS sources; no paid feeds, no scraping of unofficial economic calendars, no Parallax compatibility import path, and no Parallax import of calendar observations into numeric `macro-core`.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/AGENTS.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/official_calendar.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Kill/defer criteria**: Official source pages stop exposing parsable public release dates or Parallax ingestion requires a new non-numeric event fact table.
- **Eval/repair signal**: `macro-calendar-core` appears in `macro-core`, the default bundle becomes partial for reachable official schedule pages, `days_until` is non-deterministic in CLI bundle runs, or provenance omits official source URLs.
- **Status**: [x]

### Task 15 — Delete Runtime Static Source-Backlog Gaps

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_gap_payloads.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 3, Task 7, Task 9
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_gap_payloads.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_has_no_static_source_backlog_gap_codes tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes -q && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Remove all static source-backlog `gap_codes` from retained module configs. Delete backend catalog-gap label/remediation dictionaries for retired source backlog codes so old codes fall through to generic data-gap handling. Remove frontend `rates/expectations` proxy-readiness branching driven by `fed_funds_futures_missing` / `fomc_probability_feed_missing`, and remove those future gaps from macro fixtures. Keep actual missing/stale observation gaps and chart concept gaps intact.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_daily_brief.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Source backlog stays in SDD/spec docs only; runtime module pages must not emit future-integration gaps for unavailable products, and frontend must not maintain special labels or proxy-page states for those retired codes.
- **On-demand context**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/FRONTEND.md`
- **Kill/defer criteria**: A retained module becomes unable to report real missing observations without static backlog gaps.
- **Eval/repair signal**: Any retained module has non-empty static `gap_codes`, raw retired source-backlog codes appear in product text, or `rates/expectations` renders as a proxy/deferred page because of unavailable Fed futures/FOMC probability sources.
- **Status**: [x]

### Task 16 — Add macrodata Treasury Auction Result Bundle

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 10, Task 11
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Conflict set**: `coordinate with macrodata-cli for external macrodata provider/bundle changes; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_http_client.py::test_http_client_disables_environment_proxy_settings tests/provider/test_treasury_auction_provider.py tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_runtime_wires_treasury_auction_provider tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_treasury_auction_core_bundle_fetch_uses_official_fiscaldata -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add `treasury_auction` provider backed by the official U.S. Treasury FiscalData `auctions_query` API. Disable `httpx` environment proxy use in `MacrodataHttpClient` because the project runtime succeeds with `trust_env=False` while `trust_env=True` times out on FiscalData TLS handshake. Add standalone `treasury-auction-core` for completed 2Y/10Y/30Y auction high yield, bid-to-cover, and indirect bidder accepted percentage. Do not add these event observations to numeric `macro-core`, and do not restore the Parallax `rates/auctions` route in this task.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check . && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run macrodata bundle fetch treasury-auction-core --asof 2026-06-16`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Treasury FiscalData; no paid feeds, no unofficial auction calendar scraping, no auction-tail calculation without a reliable when-issued yield source, no Parallax compatibility import path, and no Parallax import of auction observations into numeric `macro-core`.
- **On-demand context**: `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/treasury_auction.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/gateway/http_client.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- **Kill/defer criteria**: FiscalData auction query becomes unreachable from the project runtime or does not expose completed auction result fields needed for high yield, bid-to-cover, and indirect bidder share.
- **Eval/repair signal**: `treasury-auction-core` appears in `macro-core`, live smoke returns partial/unavailable for current 2Y/10Y/30Y result metrics, or a deleted auction page route is restored instead of keeping auction results in event-aware overview rendering.
- **Status**: [x]

### Task 17 — Import And Render Official Macro Events

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 16
- **Touch set**: `src/parallax/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_api_macro_contract.py`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap; coordinate with macrodata-cli for external event bundle contracts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_event_targets_refresh_without_numeric_snapshot tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q && cd web && npm run test -- MacroModulePages.test.tsx -t "renders overview page grammar" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add event-provider series mappings for `macro-calendar-core` and `treasury-auction-core` that are importable into `macro_observations` as `event:*` concepts while remaining outside numeric `MACRO_CORE_CONCEPTS`. Let `MacroViewProjectionWorker` refresh event-only series rows without rebuilding the `macro_regime_v4` snapshot. Add overview module event concepts, backend `decision_console.event_catalysts`, and frontend rendering in the existing decision console.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py -q && cd web && npm run test -- MacroModulePages.test.tsx MacroRatesWorkbench.test.tsx macroPageRegistry.test.ts macroRoutes.test.ts --run && npm run lint && npm run test:architecture && npm run typecheck`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add event observations to `macro-core`, do not expand numeric readiness/scoring counts, do not restore `rates/auctions` or any deleted Fed/calendar proxy page, and do not let the frontend derive catalyst text from raw series values.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/official_calendar.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/treasury_auction.py`
- **Kill/defer criteria**: Event observations require a new persistent table or scheduled multi-bundle runtime orchestration beyond the current import/projection path.
- **Eval/repair signal**: `event:*` concepts appear in `MACRO_CORE_CONCEPTS`, event-only dirty targets rebuild numeric snapshots, deleted macro routes reappear, or the overview decision console shows raw provider keys instead of readable catalysts.
- **Status**: [x]

### Task 18 — Schedule Official Event Bundles In Macro Sync

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_sync_service.py`, `src/parallax/platform/config/settings.py`, `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `src/parallax/app/runtime/worker_manifest.py`, `tests/unit/domains/macro_intel/test_macro_sync_service.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`, `tests/architecture/test_worker_runtime_contracts.py`, `docs/SETUP.md`, `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 16, Task 17
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/**`, `src/parallax/platform/config/settings.py`, `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `src/parallax/app/runtime/worker_manifest.py`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`, `tests/architecture/test_worker_runtime_contracts.py`, `docs/SETUP.md`, `docs/CONTRACTS.md`, `docs/WORKERS.md`, `docs/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `coordinate with macrodata-cli for external event history command changes; coordinate with 2026-06-12-kappa-cqrs-governance-root-fix for active macro overlap`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces tests/unit/test_bundles.py::test_bundle_history_marks_empty_series_windows_unavailable -q && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && uv run pytest tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_schedules_all_configured_product_bundles tests/unit/test_worker_settings.py::test_default_workers_yaml_contains_canonical_worker_defaults tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_configured_sync_bundles -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add first-class `macrodata bundle history macro-calendar-core` and `macrodata bundle history treasury-auction-core` CLI surfaces. Mark bundle-history windows with zero observations as `unavailable`/`no_observations` instead of `ok`. Replace Parallax `workers.macro_sync.bundle_name` with formal `bundle_names`; Task 17 defaulted it to `macro-core`, `macro-calendar-core`, and `treasury-auction-core`, and Task 31 extends the current default with `fed-text-core`. `MacroSyncService.enqueue_due_windows` schedules each configured bundle through the existing `macro_sync_windows` table. Extend macrodata runtime diagnostics so `macro status` reports missing configured sync bundles when the installed `macrodata-cli` package is stale. Pin Parallax to macrodata-cli Git rev `c59b298994d111f36b4eef292790714057db42c0` so normal `uv run` installs the event-history-capable package for the Task 17 bundles.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/cli/test_bundle_commands.py tests/unit/test_bundles.py tests/provider/test_official_calendar_provider.py tests/provider/test_treasury_auction_provider.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/macrodata/surfaces/cli.py src/macrodata/app/services.py tests/cli/test_bundle_commands.py tests/unit/test_bundles.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run macrodata bundle history macro-calendar-core --start 2026-06-16 --end 2026-07-31 && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run macrodata bundle history treasury-auction-core --start 2026-05-01 --end 2026-06-16 && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_scheduler.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_sync_service.py src/parallax/platform/config/settings.py src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No service fallback to old `bundle_name`; no host-local macrodata checkout dependency in Parallax runtime; no restored macro proxy pages; event bundles remain outside numeric `macro-core` and numeric readiness.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/WORKERS.md`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`, `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/surfaces/cli.py`
- **Kill/defer criteria**: The packaged macrodata release cannot expose event bundle history commands, or operators decide event catalysts should stay manual import only.
- **Eval/repair signal**: `macro_sync` only schedules `macro-core`, old `bundle_name` remains a runtime setting, `macro status` cannot identify stale macrodata packages missing event bundles, or zero-observation event history windows report `ok`.
- **Status**: [x]

### Task 19 — Record Timsun Parity Audit And Successor Source Plan

- **File(s)**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`, `docs/TECH_DEBT.md`
- **Owner**: parent agent
- **Depends on**: Task 12, Task 18
- **Touch set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/**`, `docs/TECH_DEBT.md`
- **Conflict set**: `docs/sdd/features/active/2026-06-16-macro-decision-console/**; docs/TECH_DEBT.md`
- **Failing test first**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Capture the live retained-module audit and timsun benchmark read. Split remaining parity work into source-backed successor tasks: trade-map reliability, Fed text lane, rate probabilities, volatility term structure, crypto derivatives, options/GEX/breadth, global-dollar funding, subsurface funding, credit microstructure, and economy nowcast/surprise. Keep the source backlog in docs only; do not add hidden routes, static runtime gap labels, or compatibility code for deleted pages.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check`
- **Review owner**: parent agent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Source candidates must distinguish public official feeds from paid/licensed feeds; no secret values, scraped-workaround assumptions, restored deleted routes, or frontend proxy states.
- **On-demand context**: `docs/SECURITY.md`, `docs/DESIGN_DISCIPLINE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: A source cannot be legally or technically evaluated enough to classify public vs paid, in which case it stays `research required` and no route is restored.
- **Eval/repair signal**: SDD docs advertise parity without a source, route compatibility code reappears, or current live audit contradicts the retained-module readiness claim.
- **Status**: [x]

### Task 20 — Add Trade Map And Asset Cross-Asset Historical Review

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; src/parallax/app/surfaces/api/routes_macro.py; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_module_read_adds_asset_class_diagnostics_from_module_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_asset_class_diagnostics_from_module_history -q`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders bonds asset-class diagnostics"`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders fx asset-class diagnostics"`; `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders crypto asset-class diagnostics"`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add a backend-only five-asset 60-day historical review to overview `decision_console.trade_map` for `NDX`, `BTC`, `GOLD`, `SPX`, and `TLT`. Load these histories through the overview module API using the existing macro observation projection, not frontend provider calls. Render compact history lines in the Trade Map panel and add explicit HY OAS widening/tightening labels so the overview does not show `待确认信号` for known rules. The 2026-06-17 continuations also add backend `asset_diagnostics` to retained `assets` for SPX, TLT, DXY, WTI, BTC, VIX, and HY OAS, then render it as `跨资产诊断` directly after the core asset market board; retained `assets/equities` now emits `asset_class_diagnostics` from SPX, NDX, RUT, QQQ, IWM, and CFTC S&P net non-commercial positioning, rendered as `美股风险诊断` directly after the market evidence; retained `assets/bonds` now emits `asset_class_diagnostics` from TLT, IEF, LQD, HYG, HY OAS, and IG OAS, rendered as `债券风险诊断` from the backend payload label; retained `assets/commodities` now emits `asset_class_diagnostics` from WTI, Brent, NatGas, Gold, and Copper, rendered as `商品冲击诊断` from the backend payload label; retained `assets/fx` now emits `asset_class_diagnostics` from DXY, Broad USD, EURUSD, USDJPY, USDCNY, and UUP, rendered as `美元压力诊断` from the backend payload label; retained `assets/crypto` now emits `asset_class_diagnostics` from BTC/ETH plus OKX/Deribit OI, funding, basis, and DVOL leverage evidence, rendered as `加密 beta 诊断` from the backend payload label, with missing derivatives groups surfaced as module-reference data-health gaps. These slices use existing projected macro observations and do not restore `assets/crypto-derivatives`, OKX/Deribit derivative shells, options/GEX, standalone CFTC, CDS, commodity proxy shells, or any hidden compatibility route.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side backtest or macro-regime math, no new provider calls in API request path beyond reading projected macro observation rows, no restored deleted routes, and no hidden compatibility fields.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: Required five-asset histories are unavailable in projected macro observations, or the review requires a new table beyond this slice.
- **Eval/repair signal**: `/macro` lacks five-asset history rows, Trade Map shows `待确认信号` for known HY OAS rules, frontend computes returns locally, overview API returns only latest observations for the Trade Map targets, or `/macro/assets` lacks a backend-fed `跨资产诊断` region despite SPX/TLT/DXY/WTI/BTC/VIX/HY OAS history.
- **Status**: [x]

### Task 21 — Add Trade Map Paper P&L And Action Checklist

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 20
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add a backend-generated `$10K` equal-weight paper map to overview `decision_console.trade_map` whenever the five-asset historical review is available. Report paper P&L, P&L percentage, max adverse dollars, risk temperature, and an action checklist derived from backend confirm/invalidate conditions plus a position-review row. Render the paper map and checklist in the Macro Workbench Trade Map panel without frontend-side P&L math.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side allocation/P&L/backtest math, no compatibility fields for deleted pages, and no sourced-data claims beyond persisted macro observations.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: The paper map cannot be derived deterministically from existing historical review rows, or it needs execution/broker semantics beyond a display-only decision audit.
- **Eval/repair signal**: `/macro` lacks `$10K` paper map rows, P&L is computed in React, action checklist shows raw codes, or paper P&L is presented as an executable trade.
- **Status**: [x]

### Task 22 — Add Trade Map Historical Trust And Holding-Period Review

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 21
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `historical_trust` and `holding_period_review` to overview `decision_console.trade_map` using the same five source-backed asset histories as the 60-day review. Evaluate 1D, 5D, and 20D holding periods from the first available observation to the first observation at or after each horizon. Render historical trust and holding-period rows in the Macro Workbench Trade Map panel without frontend-side return or P&L math. The 2026-06-17 continuation also structures the Trade Map panel into explicit `当前表达`, `五资产雷达`, `组合复盘`, `历史可信度`, `持有期复盘`, and `行动清单` blocks so the timsun-style reliability evidence is readable instead of a flat text run.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No automated trade execution, no frontend-side holding-period/backtest math, no new provider calls, no compatibility fields for deleted pages, and no claims beyond persisted macro observations.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: Holding-period review requires prior macro-map storage instead of current five-asset histories, in which case this becomes a successor read-model task.
- **Eval/repair signal**: `/macro` lacks historical trust or 1D/5D/20D holding rows, holding P&L is computed in React, or trust scores are shown without sample counts.
- **Status**: [x]

### Task 23 — Add Yield Curve Curve-Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`, `web/src/features/macro/ui/rates/RatesCurveDiagnostics.tsx`, `web/src/features/macro/ui/rates/RatesRealRateDiagnostics.tsx`, `web/src/features/macro/ui/rates/ratesCurveDiagnostics.css`, `web/src/features/macro/ui/rates/ratesRealRateDiagnostics.css`, `web/src/features/macro/ui/rates/macroRatesWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_module_read_adds_real_rate_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `curve_diagnostics` to `rates/yield-curve` when Treasury histories support it. Calculate 2s10s, 3m10y, and 5s30s current spread plus 1w/1m/3m changes from persisted FRED histories; classify curve shape; emit implication and invalidation text. The 2026-06-17 continuation also emits bounded spread-history series and 5Y/10Y nominal-real-breakeven tenor comparison from existing nominal Treasury, TIPS real-yield, and breakeven histories. The same continuation adds backend-generated `real_rate_diagnostics` to `rates/real-rates` from existing 5Y/10Y/30Y TIPS, 5Y/10Y breakeven, and 5Y5Y forward inflation histories, then renders it as a rates-owned decision block. Render the diagnostics after the primary chart in adjacent owner components/CSS so the route CSS budget stays below the architecture harness limit.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side curve math or macro scoring, no provider calls in React, no restored deleted rates pages, no compatibility fields, and no curve diagnosis when only a single latest point is available.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED nominal Treasury histories are unavailable from the current macro snapshot, or a requested tenor cannot be backed by nominal, real, and breakeven observations.
- **Eval/repair signal**: `rates/yield-curve` lacks a curve-diagnostics region despite source-backed histories, `rates/real-rates` lacks a real-rate diagnostics region despite source-backed TIPS/breakeven histories, display text exposes raw `rates:*` or `inflation:*` keys, source-backed spread-history/tenor/real-yield rows are omitted, curve or real-rate changes are computed in React, or `macroRatesWorkbench.css` exceeds the 500-line CSS architecture budget.
- **Status**: [x]

### Task 24 — Add Credit Stress Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_nfci_tightening_when_spreads_lag -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `credit_diagnostics` to `credit/stress` when persisted FRED/Yahoo credit histories support it. Calculate HY OAS, IG OAS, CCC-HY tail spread, HYG/LQD credit ETF relative pressure, NFCI financial conditions, adjusted NFCI, and SLOOS large-firm tightening current values plus available 1w/1m/3m or 1q changes; classify credit regime, including `credit_etf_pressure` when HYG runs behind LQD before spreads fully confirm and `financial_conditions_tightening` when NFCI tightens before spreads fully confirm; emit implication and invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf page using an adjacent workbench-owned component and CSS file, and display ETF-relative and index-valued credit rows rather than dropping them.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side credit math, no provider calls in React, no restored `credit/cds`, no hidden credit route, no compatibility fields, no fabricated CDS/TRACE/ETF-flow placeholder, no JNK duplication while HYG/LQD already cover the tradable public ETF confirmation, and no credit diagnosis when only a single latest point is available.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED credit histories are unavailable from the current macro snapshot, or TRACE/CDS/ETF liquidity evidence requires a broader credit read model.
- **Eval/repair signal**: `credit/stress` lacks a credit-diagnostics region despite source-backed histories, omits `HYG/LQD 信用 ETF` when HYG/LQD history exists, omits `NFCI 金融条件` when NFCI history exists, drops ETF-relative or index-valued credit rows in the frontend, displays raw `credit:*` keys, computes credit changes in React, or CSS architecture breakpoints drift from the frontend harness contract.
- **Status**: [x]

### Task 25 — Add Volatility VIX Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `volatility_diagnostics` to `volatility/vix` when persisted volatility histories can support it. Calculate VIX spot, VIX3M-VIX term premium, VIXY/VIXM front-end pressure, and VXN current values plus 1w/1m changes from module feature histories, then classify volatility regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf module page using an adjacent workbench-owned component and CSS file. The 2026-06-17 Cboe continuations add official Cboe historical CSV provider support in macrodata-cli for `cboe:VVIX`, `cboe:SKEW`, `cboe:VIX9D`, and `cboe:VIX1D`; bump macrodata-cli through `0.1.20` commit `739d0bab59f4ac8b905008478aeefbeb541e4a9b`; repin Parallax to that packaged dependency; map those series to required-history `vol:vvix`, `vol:skew`, `vol:vix9d`, and `vol:vix1d`; fold them into retained `volatility/vix` tiles/table/availability notes; add backend diagnostics rows for convexity, tail premium, `VIX9D-VIX` near-term event premium, and `VIX1D-VIX` same-day event premium; add `cboe -> Cboe` source labels; and make leaf-module API reads use persisted concept history rather than only latest rows.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side volatility math, no provider calls in React, no fake VIXD/VIX1D/VIX9D/VVIX/SKEW rows, no restored volatility dashboard, no compatibility fields, and no volatility diagnosis when only a single latest point is available. MOVE rows must come from persisted `yahoo:^MOVE` macro facts, and VIX1D/VIX9D/VVIX/SKEW rows must come from official Cboe macro facts, not static UI placeholders.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/Cboe/Yahoo volatility histories are unavailable from the current macro snapshot, or true futures/options term-structure evidence requires a broader licensed volatility read model.
- **Eval/repair signal**: `volatility/vix` lacks a volatility-diagnostics region despite source-backed histories, omits VIX1D/VIX9D/VVIX/SKEW after projected Cboe facts exist, displays raw `vol:*` keys or `未知来源` for Cboe facts, computes volatility changes in React, or the deleted volatility dashboard route is restored instead of keeping the source-backed read on the retained VIX module.
- **Status**: [x]

### Task 26 — Add Liquidity RRP/TGA Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `liquidity_diagnostics` to `liquidity/rrp-tga` when persisted liquidity histories can support it. Calculate SOFR-IORB corridor pressure, SOFR-TGCR repo-depth pressure, SOFR underlying volume, RRP buffer, TGA fiscal cash, and net liquidity current values plus 1w/1m changes when enough history exists, then classify liquidity regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board in the generic leaf module page. Replace the duplicated credit/volatility-specific diagnostic panels with one shared macro signal diagnostics panel and delete the redundant old components/CSS. The 2026-06-17 continuation adds NY Fed Markets API `BGCR`, `TGCR`, `SOFR_VOLUME`, `BGCR_VOLUME`, and `TGCR_VOLUME` to external macrodata-cli `liquidity-core` / `macro-core`, repins Parallax to macrodata-cli `0.1.16` commit `06b94b1ccf5840ed34205498c4fddd43f796bb9d`, maps the five concepts into `liquidity/rrp-tga`, and makes module views supplement missing snapshot features from projected module observations so freshly projected optional repo-depth facts display before long-history bootstrap completes.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side liquidity math, no provider calls in React, no fake 7d/14d future liquidity heatmap, no restored `liquidity/global-dollar` or `liquidity/subsurface`, no compatibility fields, and no liquidity diagnosis when all rows have only a single latest point. Single-point repo-depth facts may still render as tiles/table rows and diagnostic rows when other liquidity histories support the diagnostic block.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: NY Fed/FRED/Treasury liquidity histories are unavailable from the current macro snapshot, or future Treasury/Fed event heatmap and projected liquidity impact require a broader event read model.
- **Eval/repair signal**: `liquidity/rrp-tga` lacks a liquidity-diagnostics region despite source-backed histories, omits projected NY Fed BGCR/TGCR/volume facts from tiles and tables, displays raw `liquidity:*` keys, computes SOFR-IORB/SOFR-TGCR/net liquidity in React, or a deleted liquidity page is restored instead of keeping the source-backed read on the retained RRP/TGA module.
- **Status**: [x]

### Task 27 — Add Inflation Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/src/features/macro/ui/workbench/macroSignalDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_module_read_adds_inflation_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `inflation_diagnostics` to `economy/inflation` when persisted inflation histories can support it. Calculate CPI YoY, Core CPI YoY, PPI YoY, and 10Y breakeven current/change rows from module feature histories, then classify inflation regime and emit implication/invalidation text. Render the diagnostics between the primary market evidence and driver board through the generic macro signal diagnostics panel.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side inflation math, no provider calls in React, no fake actual-vs-consensus or surprise rows, no restored economy calendar/surprise page, no compatibility fields, and no inflation diagnosis when yearly history is unavailable.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED inflation histories are unavailable from the current macro snapshot, or surprise/consensus/revision evidence requires a broader licensed or official release read model.
- **Eval/repair signal**: `economy/inflation` lacks an inflation-diagnostics region despite source-backed histories, displays raw `inflation:*` keys, computes YoY inflation in React, or a proxy-only surprise/calendar page is restored instead of keeping the source-backed read on the retained inflation module.
- **Status**: [x]

### Task 28 — Add Employment Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/**`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_module_read_adds_employment_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `employment_diagnostics` to `economy/employment` when persisted labor histories can support it. Calculate unemployment-rate change, payroll monthly gain/deceleration, initial-claims change, job-openings change, and wage YoY/current-change rows from module feature histories, then classify labor-market regime and emit implication/invalidation text. Render the diagnostics between primary market evidence and driver board through the generic macro signal diagnostics panel.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side employment math, no provider calls in React, no fake actual-vs-consensus or payroll surprise rows, no restored economy calendar/surprise page, no compatibility fields, and no employment diagnosis when history is insufficient for monthly change or wage YoY.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/BLS labor histories are unavailable from the current macro snapshot, or consensus/revision/surprise evidence requires a broader official-release or licensed calendar read model.
- **Eval/repair signal**: `economy/employment` lacks an employment-diagnostics region despite source-backed histories, displays raw `labor:*` keys, computes labor-market changes in React, or a proxy-only surprise/calendar page is restored instead of keeping the source-backed read on the retained employment module.
- **Status**: [x]

### Task 29 — Add GDP Growth Diagnostics Workbench

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/pages/MacroLeafModulePage.tsx`, `web/src/features/macro/ui/workbench/MacroSignalDiagnosticsPanel.tsx`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/**`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/**`, `web/src/features/macro/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `growth_diagnostics` to `economy/gdp` when persisted growth histories can support it. Calculate real GDP YoY/quarterly deceleration, source-backed GDPNow SAAR nowcast, industrial-production YoY/current change, housing-starts level/change, real PCE YoY/current change, and retail-sales YoY/current change from module feature histories, then classify growth regime and emit implication/invalidation text. Render the diagnostics between primary market evidence and driver board through the generic macro signal diagnostics panel. The 2026-06-17 continuation adds `fred:GDPNOW` to external macrodata-cli `economy-core`, repins Parallax to macrodata-cli `0.1.15` commit `a01ed678ad578cd6406f93b20558da4ccd1fc660`, maps it to `economy:gdp_nowcast`, and keeps it optional so missing nowcast history never downgrades global macro readiness.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py tests/unit/test_runtime.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side growth math, no provider calls in React, no fake nowcast, no actual-vs-consensus or surprise rows, no restored `economy/consumer` or separate surprise/calendar page, no compatibility fields, and no growth diagnosis when yearly history or current/quarter change evidence is insufficient.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: FRED/BEA/BLS growth histories are unavailable from the current macro snapshot, or consensus/revision/surprise evidence requires a broader official-release or licensed calendar read model.
- **Eval/repair signal**: `economy/gdp` lacks a growth-diagnostics region despite source-backed histories, displays raw `economy:*` or `consumer:*` keys, computes GDP/consumption changes in React, or a proxy-only consumer/surprise page is restored instead of keeping the source-backed read on the retained GDP module.
- **Status**: [x]

### Task 30 — Add Fed Funds Corridor Diagnostics Workbench

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/MacroRatesModulePage.tsx`, `web/src/features/macro/ui/rates/RatesPolicyDiagnostics.tsx`, `web/src/features/macro/ui/rates/ratesPolicyDiagnostics.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 19
- **Touch set**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/src/features/macro/ui/rates/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/**; web/src/features/macro/**; web/tests/fixtures/macroFixture.ts`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_nyfed_unsecured_funding_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_absorbs_nyfed_unsecured_funding_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add backend-generated `policy_diagnostics` to `rates/fed-funds` when persisted policy-rate histories can support it. Calculate target range, EFFR position inside the range, EFFR-IORB, SOFR-EFFR, SOFR 30D-EFFR, and DFF/EFFR drift from module feature histories, then classify policy-corridor regime and emit implication/invalidation text. Render the diagnostics between the primary rates visual and decision-support board in the rates workbench. The 2026-06-17 continuation adds NY Fed Markets API `EFFR`, `OBFR`, `EFFR_VOLUME`, and `OBFR_VOLUME` to external macrodata-cli `rates-market-core` / `macro-core`, repins Parallax to macrodata-cli `0.1.17` commit `ac06e171833a99e19761dc69a2e6a222d7f80754`, maps NY Fed EFFR into the existing `fed:effr` concept with higher source priority than the FRED mirror, and folds `fed:obfr`, `fed:effr_volume`, and `fed:obfr_volume` into retained `rates/fed-funds` diagnostics/table evidence instead of restoring any Fed or subsurface route.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_sync_service.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py && cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run && npm run typecheck && npm run lint && npm run format:check`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend-side policy-rate math, no provider calls in React, no fake FedWatch probabilities, no restored Fed statements/speeches, `rates/auctions`, `rates/expectations`, or `liquidity/subsurface` route, no compatibility fields, and no policy diagnosis when current corridor or spread evidence is insufficient. Short-history NY Fed funding-depth concepts are displayable but optional for global history readiness.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/FRONTEND.md`, `docs/CONTRACTS.md`
- **Kill/defer criteria**: EFFR/IORB/SOFR histories are unavailable from the current macro snapshot, NY Fed unsecured reference-rate endpoints stop returning rate/volume payloads, or meeting-date probability evidence requires an approved CME/Bloomberg/legal source lane.
- **Eval/repair signal**: `rates/fed-funds` lacks a policy-corridor diagnostics region despite source-backed histories, omits OBFR/EFFR/OBFR volume rows after successful NY Fed sync, displays raw `fed:*` or `liquidity:*` keys, computes policy spreads in React, or a proxy-only Fed/FOMC/subsurface page is restored instead of keeping the source-backed read on the retained Fed funds module.
- **Status**: [x]

### Task 31 — Add Official Fed Text Event Bundle

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `src/parallax/platform/config/settings.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `tests/unit/domains/macro_intel/test_macro_sync_service.py`, `tests/unit/test_worker_settings.py`, `tests/unit/test_cli_macro_commands.py`
- **Owner**: parent agent
- **Depends on**: Task 19, Task 24
- **Touch set**: `src/parallax/domains/macro_intel/**`, `src/parallax/platform/config/settings.py`, `tests/unit/domains/macro_intel/**`, `tests/unit/test_*macro*`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_fed_text_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q`; `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_fed_text_events_with_stable_document_series_keys tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: In the external macrodata-cli checkout, add provider `official_fed_text` and bundle `fed-text-core` for official Federal Reserve FOMC statement, minutes, monetary-policy press-release, and speech documents. Reject legacy aliases such as `fed_page_latest`. In Parallax, map those series to `event:fed_fomc_statement`, `event:fed_fomc_minutes`, `event:fed_monetary_policy_press_release`, and `event:fed_speech`, persist same-day Fed documents under stable URL-derived series keys, render their titles as overview `event_catalysts`, and add `fed-text-core` to the default `workers.macro_sync.bundle_names`.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/provider/test_official_fed_text_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/platform/config/settings.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Federal Reserve sources; do not scrape/parse unofficial summaries; do not restore `fed/statements` or `fed/speeches`; do not add compatibility aliases; do not put Fed text into numeric `MACRO_CORE_CONCEPTS`; preserve source URL/title/timestamp in provenance; avoid DB uniqueness collisions for same-day speeches.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, macrodata-cli reference catalog in the external checkout
- **Kill/defer criteria**: Federal Reserve official pages/RSS become inaccessible from this runtime, or text delta/scoring is required before catalyst-only rendering can ship.
- **Eval/repair signal**: `fed-text-core` appears as a numeric macro-core concept, deleted Fed routes return a module shell, two speeches on the same date overwrite each other, or live `macro status` cannot identify an installed macrodata package that lacks `fed-text-core`.
- **Status**: [x]

### Task 32 — Repin Fed Text Runtime And Allow Text Event Projection

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/20260616_0180_macro_event_text_series_nullable.py`, `tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/test_postgres_schema.py`
- **Owner**: parent agent
- **Depends on**: Task 31
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/**`, `tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/test_postgres_schema.py`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/repositories/macro_intel_repository.py; src/parallax/platform/db/alembic/versions/**; tests/unit/domains/macro_intel/test_macro_migration_contract.py; coordinate with 2026-06-09-agent-playbook-skill-hard-cut for repository and migration-contract overlap`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py::test_partition_refresh_allows_text_event_rows_without_numeric_values tests/unit/test_postgres_schema.py::test_macro_event_text_series_nullable_migration_allows_text_event_rows -q`; live `uv run parallax macro sync --bundle fed-text-core --start 2026-04-01 --end 2026-06-16`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: In macrodata-cli, add per-request HTTP timeout support and give official Federal Reserve text pages/RSS a longer timeout so the speeches feed does not falsely mark `fed-text-core` partial. In Parallax, repin macrodata-cli to commit `ba8cf292afb77bfd554e0a0ebf1f3d0b0fc040fc`, make `macro_observation_series_rows.value_numeric` nullable, and update the projection refresh query to include non-numeric `event:*` rows while preserving the numeric-only filter for ordinary macro series.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/unit/test_postgres_schema.py::test_macro_event_text_series_nullable_migration_allows_text_event_rows -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add host-local macrodata checkout fallbacks, hidden Fed routes, compatibility aliases, or numeric sentinel values for text events. Text facts remain source-backed `event:*` rows with null `value_numeric`; same-day document identity remains URL-derived in facts.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, external macrodata-cli `official_fed_text` provider
- **Kill/defer criteria**: Federal Reserve official RSS/feed access repeatedly fails even with the extended timeout, or making text event read-model rows nullable breaks current numeric chart paths.
- **Eval/repair signal**: live `fed-text-core` sync reports partial/missing `official_fed_text:speech_latest`, `macro status` reports missing `fed-text-core`, `event:fed_speech` facts are absent after sync, or overview catalysts omit Fed text rows.
- **Status**: [x]

### Task 33 — Make Event Catalysts Inspectable

- **File(s)**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`, `web/src/features/macro/ui/workbench/macroWorkbench.css`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 32
- **Touch set**: `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `tests/unit/test_api_macro_contract.py`, `web/src/features/macro/model/macroWorkbenchModel.ts`, `web/src/features/macro/ui/workbench/**`, `web/tests/fixtures/macroFixture.ts`, `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/services/macro_module_views.py; web/src/features/macro/**; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_market_event_flow -q`; `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Preserve `source_url` from official event provenance in overview event rows; preserve Fed text `document_type` and speech `speaker` metadata when available; map those fields through the macro workbench model and render source-backed rows in sibling `module_read.market_event_flow` instead of restoring old `decision_console.event_catalysts` or `decision_console.event_heatmap` fields. Classify upcoming calendar, auction-calendar, auction-result, Fed-text, and source-backed news rows by window, severity, category, impact, watch text, and source URL. Keep the Fed text lane catalyst/event-flow-only and do not restore deleted Fed routes, auctions routes, calendar/surprise pages, or text scoring.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_market_event_flow -q && cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run && npm run typecheck && npm run lint && npm run format:check && cd .. && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No frontend provider calls, no React-side macro or event scoring, no Fed text route restoration, no auctions route restoration, no calendar/surprise route restoration, no hidden compatibility aliases, no auction-tail fabrication, no actual/consensus/surprise placeholders, no numeric sentinel values for text events, no source URLs invented when provenance lacks one, and no legacy `decision_console.event_catalysts` / `decision_console.event_heatmap` compatibility fields.
- **On-demand context**: `docs/FRONTEND.md`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Official source provenance is absent from imported event rows, or product needs full text-delta scoring before catalyst links are acceptable.
- **Eval/repair signal**: Overview `market_event_flow` rows lack source URLs when provenance has them, Fed speech rows lack speaker metadata despite title/provenance support, the old `decision_console.event_catalysts` / `event_heatmap` fields reappear, or a deleted route is restored.
- **Status**: [x]

### Task 34 — Add BLS Official Calendar Catalysts

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 14, Task 17, Task 33
- **Touch set**: `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/domains/macro_intel/_constants.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Extend macrodata-cli `official_calendar` with official BLS CPI, Employment Situation, and PPI release schedule pages, add those three series to catalog and `macro-calendar-core`, and map them in Parallax to `event:bls_cpi_next`, `event:bls_employment_next`, and `event:bls_ppi_next` metadata. Preserve BLS reference period and release time in provenance. Keep the data catalyst-only in the overview decision console.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces -q && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official BLS pages, no unofficial economic-calendar scraping, no restored calendar/surprise route, no actual-vs-consensus or surprise fields, no Parallax compatibility alias, and no import of BLS event observations into numeric `MACRO_CORE_CONCEPTS`.
- **On-demand context**: external macrodata-cli official-calendar provider/catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Official BLS schedule pages stop exposing parsable public release rows or require a source contract incompatible with automated public ingestion.
- **Eval/repair signal**: `macro-calendar-core` omits one of the three BLS schedule events, BLS rows lack `source_url` or `reference_period`, event concepts enter numeric `MACRO_CORE_CONCEPTS`, or a deleted calendar/surprise page is restored instead of rendering overview catalysts.
- **Status**: [x]

### Task 35 — Detect Stale Event Bundle Series In Macro Status

- **File(s)**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 34
- **Touch set**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `src/parallax/integrations/macrodata/runner.py; src/parallax/app/surfaces/cli/commands/macro.py; tests/unit/test_cli_macro_commands.py`
- **Failing test first**: `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_event_bundle_series tests/unit/test_cli_macro_commands.py::test_macro_status_requires_importable_event_bundle_series -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Extend `macrodata_runtime_state` so status checks expected series membership per configured bundle, not only bundle names or numeric `macro-core` membership. Have `parallax macro status` pass all importable provider series plus per-bundle requirements for `macro-core`, `macro-calendar-core`, `treasury-auction-core`, and `fed-text-core`.
- **Verification**: `cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_cli_macro_commands.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/test_cli_macro_commands.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add a host-local macrodata fallback, do not mark stale packages usable merely because a bundle name exists, and do not require event series inside numeric `macro-core`.
- **On-demand context**: `src/parallax/integrations/macrodata/runner.py`, `src/parallax/app/surfaces/cli/commands/macro.py`, `tests/unit/test_cli_macro_commands.py`
- **Kill/defer criteria**: macrodata-cli cannot expose bundle series lists from installed package metadata or imports.
- **Eval/repair signal**: `macro status` reports `required_bundles_available=true` and no missing bundle-series while installed `macro-calendar-core` lacks the BLS event series required by Parallax constants.
- **Status**: [x]

### Task 36 — Repin BLS Calendar Runtime And Verify Live Catalysts

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Owner**: parent agent
- **Depends on**: Task 34, Task 35
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/services/macro_module_views.py; tests/unit/domains/macro_intel/test_macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_show_bls_release_time_and_reference_period -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: In the external macrodata-cli checkout, bump the package to `0.1.12`, commit and push the BLS official-calendar implementation at Git rev `25ba5281d04a0ddc81ab6a07c4a5784b698100f9`, and repin Parallax to that versioned Git source. Keep runtime sync portable by using the packaged Git dependency, not a host-local checkout. Extend overview calendar catalyst descriptions to read source-provided `event_time_et` and `reference_period`, so BLS CPI, Employment Situation, and PPI catalysts show release time and reference period in the decision console.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/unit/test_runtime.py tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_show_bls_release_time_and_reference_period -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Do not add host-local macrodata fallback paths, do not mark stale packages usable, do not put BLS events in numeric `MACRO_CORE_CONCEPTS`, do not restore calendar/surprise pages, and do not fabricate actual/consensus/prior/revision values.
- **On-demand context**: external macrodata-cli `official_calendar` provider/catalog/bundle tests, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `tests/architecture/test_project_structure.py`
- **Kill/defer criteria**: macrodata-cli BLS branch cannot be published or pinned as a portable Git source, or live runtime cannot fetch official BLS schedule pages from the packaged dependency.
- **Eval/repair signal**: `macro status` reports missing BLS bundle series, `macro-calendar-core` live sync imports no BLS facts in an unrestricted runtime, BLS facts fail to project into `macro_observation_series_rows`, or overview market-event rows omit BLS release time/reference period despite provenance carrying it.
- **Status**: [x]

### Task 37 — Add MOVE Rates-Volatility Proxy To Volatility Read

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 25, Task 36
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/_constants.py; src/parallax/domains/macro_intel/services/macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series tests/unit/test_catalog.py::test_catalog_documents_public_macro_terminal_proxies tests/unit/test_runtime.py::test_package_version_advances_for_move_proxy_release -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add `yahoo:^MOVE` to macrodata-cli catalog and `volatility-core`, bump macrodata-cli to `0.1.13`, commit and push Git rev `1fde95d5b4ddff9bdec60cc9e1d25ec9027b10ce`, and repin Parallax to that packaged Git dependency. Map `yahoo:^MOVE` to `vol:move`, add it to retained `volatility/vix` chart/table evidence, and emit a backend MOVE diagnostics row from persisted history. Keep `vol:move` out of the global 126-point history gate so the new proxy improves the volatility module without making the whole macro snapshot partial during bootstrap.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: No restored volatility dashboard, no hidden gap or compatibility route, no frontend provider calls, no fake MOVE row, no claim that Yahoo `^MOVE` is an official licensed ICE feed, and no global snapshot downgrade while the proxy has short bootstrap history.
- **On-demand context**: external macrodata-cli catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Yahoo `^MOVE` disappears from public market data, or product requires official ICE/Bloomberg redistribution before displaying any rates-vol proxy.
- **Eval/repair signal**: `macro status` reports missing `yahoo:^MOVE`, `volatility/vix` has no MOVE row after `macro-core` sync, MOVE appears as a static UI row, or adding MOVE makes `latest_snapshot.status` partial solely because the proxy lacks 126 historical points.
- **Status**: [x]

### Task 38 — Add Treasury Auction Calendar Catalysts

- **File(s)**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- **Owner**: parent agent
- **Depends on**: Task 17, Task 36
- **Touch set**: `pyproject.toml`, `uv.lock`, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `tests/architecture/test_project_structure.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py`, `tests/unit/domains/macro_intel/test_macro_module_views.py`, `docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Conflict set**: `pyproject.toml; uv.lock; src/parallax/domains/macro_intel/_constants.py; src/parallax/domains/macro_intel/services/macro_module_views.py; tests/unit/domains/macro_intel/test_macro_module_views.py; docs/sdd/features/active/2026-06-16-macro-decision-console/**`
- **Failing test first**: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_treasury_auction_provider.py::test_treasury_auction_latest_returns_next_nominal_auction_from_official_tentative_schedule tests/provider/test_treasury_auction_provider.py::test_treasury_auction_range_returns_nominal_auction_calendar_without_tips_rows tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_package_version_advances_for_treasury_auction_calendar_release -q`; `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_treasury_auction_calendar_event_concepts tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q`; `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_prioritize_near_upcoming_treasury_auction_calendar -q`
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Extend macrodata-cli `treasury_auction` with official Treasury tentative schedule XML events for next nominal 2Y/10Y/30Y auctions, keep completed auction result metrics in the same first-class `treasury-auction-core` event bundle, bump macrodata-cli to `0.1.14`, commit and push Git rev `a90da8c3f4c7139924043d9d496493ded4326d50`, and repin Parallax to that packaged dependency. Map the three new series to `event:treasury_auction_*_next` concepts, render them as `auction_calendar` overview catalysts with announcement/settlement/reopening details, and sort event catalysts by nearest upcoming calendar risk before truncating so Treasury supply events are not hidden behind source-order noise.
- **Verification**: `cd /Users/qinghuan/Documents/code/macrodata-cli && UV_CACHE_DIR=/tmp/parallax-uv-cache PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' uv run pytest tests/provider/test_treasury_auction_provider.py tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py -q && RUFF_CACHE_DIR=/tmp/parallax-ruff-cache UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src tests && cd /Users/qinghuan/Documents/code/parallax/.worktrees/macro-decision-console && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py -q && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py`
- **Review owner**: parent agent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Use only official Treasury sources; no unofficial auction calendar scraping, no restored `rates/auctions` route, no auction-tail calculation without when-issued yield, no host-local macrodata fallback, no compatibility aliases, and no event observations in numeric `MACRO_CORE_CONCEPTS`.
- **On-demand context**: external macrodata-cli `treasury_auction` provider/catalog/bundle tests, `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/services/macro_module_views.py`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- **Kill/defer criteria**: Treasury tentative schedule XML or FiscalData upcoming calendar source stops exposing stable public fields, or product requires auction-tail analysis before showing any supply calendar.
- **Eval/repair signal**: `macro status` reports missing `treasury_auction:*_next_auction_days`, live `treasury-auction-core` sync imports no upcoming auction facts, overview catalysts omit upcoming Treasury supply events despite projected rows, a deleted auction route is restored, or auction calendar events enter numeric macro scoring.
- **Status**: [x]

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

The frontend maps and renders backend fields only: label, detail, 24h/72h window label, severity label, source label, and primary-source link when present. It does not compute event severity, scan providers, infer windows from dates, or add placeholder catalysts. Deleted calendar, auction, Fed text, and weak macro routes remain hard-deleted; no hidden route, compatibility shell, frontend provider call, React-side catalyst scoring, auction-tail placeholder, or actual/consensus/surprise row was added.

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

## 2026-06-22 Continuation Note — Scenario Trigger Display Contract Hard Cut

This continuation removes scenario-side trigger display inference. Macro
triggers now leave `macro_regime_engine` with explicit `label`, `node`, `kind`,
and `indicator_keys`; `macro_scenario_engine` no longer derives operator-facing
labels or sections from naked trigger codes.

Bare trigger payloads such as `{code: "sofr_above_iorb"}` are now ignored by
scenario confirmations and top changes instead of being rewritten into a
complete decision-console signal. Source labels and severity labels in scenario
feature-change rows are also constrained to known explicit metadata instead of
falling back to raw provider names or default medium severity.

## 2026-06-22 Continuation Note — Module View Scenario Signal Fallback Hard Cut

This continuation removes the matching `macro_module_view_v3` fallback layer for
scenario signals. Overview evidence, structured market lines, future catalysts,
watchlist rules, and top-change compaction now require explicit backend labels;
top-change rows also require explicit `kind`.

Known codes such as `term_premium_pressure`, `real_yield_breakout`, or
`ten_year_yield_reverses` no longer become operator-facing text inside
`macro_module_views.py` when scenario payloads omit display metadata.

## 2026-06-22 Continuation Note — Trade Map Action Checklist Code-List Hard Cut

This continuation removes the remaining Trade Map action-checklist code-list
contract. Scenario trade maps now emit explicit `action_checklist` rows with
`kind`, `label`, and `description`; they no longer expose `confirms_on` or
`invalidates_on`.

`macro_module_views.py` now consumes only those explicit checklist rows before
adding the paper-position review item. The frontend macro contract, model, UI,
fixtures, and mock API were cut over to the same single display contract, so the
workbench no longer exposes or renders separate `confirms` / `invalidates`
fields derived from backend codes.

## 2026-06-22 Continuation Note — Frontend Scenario Signal Code-Label Hard Cut

This continuation removes the frontend macro workbench scenario-signal code
label map. `MacroDecisionConsole` now requires explicit backend `label` fields
for confirmations, contradictions, and decision-console top changes; known
codes such as `sofr_above_iorb` and `hy_oas_stress` are dropped when the label is
missing instead of being translated in React.

The `SIGNAL_LABELS` table and `signalLabel(...)` helper were deleted from
`macroWorkbenchModel.ts`, and the frontend macro hard-cut architecture test now
rejects their return. This keeps scenario display ownership in the backend read
model payload rather than duplicating label policy in the browser.

## 2026-06-22 Continuation Note — Trade Map Expression Label Hard Cut

This continuation removes the remaining Trade Map expression-label mapping.
Scenario trade-map rows now carry explicit `label` values beside their stable
`expression` keys, and unlabeled trade-map rows are dropped by both backend
module views and the frontend workbench model.

`macro_module_views.py` no longer keeps `_TRADE_MAP_EXPRESSION_LABELS` or
`_trade_map_expression_label(...)`; judgement review, structured market trade
copy, and trade-map enrichment all require the scenario payload label. The
frontend `tradeExpressionLabel(...)` / `TRADE_EXPRESSION_LABELS` map was also
deleted, and fixtures/API tests now declare the label where a trade map is
intended to render.

## 2026-06-22 Continuation Note — Trade Map Checklist Kind Label Hard Cut

This continuation removes the frontend checklist-kind display map. Trade-map
`action_checklist` rows now carry explicit `kind_label` values from the backend
scenario payload, and module-view enrichment preserves only complete
`kind`/`kind_label`/`label`/`description` rows.

The paper-position review row generated by `macro_module_views.py` now also
declares `kind_label: "纸面仓位"`. `macroWorkbenchModel.ts` no longer contains
`checklistKindLabel(...)` or `CHECKLIST_KIND_LABELS`; checklist rows without a
backend `kind_label` are omitted.

## 2026-06-22 Continuation Note — Frontend Event Kind Source Label Hard Cut

This continuation removes the frontend event-kind source-label fallback from
market event flow and future catalyst rows. `macroWorkbenchModel.ts` now uses
only explicit backend `source` text in row meta; it no longer rewrites event
`kind` values such as `calendar`, `auction`, or `flow` into source labels.

Future catalysts and event-flow rows that omit `source` now render only their
explicit window and severity metadata instead of manufacturing labels such as
`官方日历`. The frontend macro hard-cut architecture test rejects restoring
`eventKindLabel(...)`.

## 2026-06-22 Continuation Note — Frontend Watchlist Kind Label Hard Cut

This continuation removes the frontend watchlist rule kind-label map. Watchlist
alert rule meta now uses explicit backend `kind_label` values only; it no
longer rewrites naked `kind` values such as `watch`, `invalidation`, or
`quality` into operator-facing labels.

Rules that omit `kind_label` may still render with their explicit window and
severity metadata, but the browser no longer manufactures labels such as
`触发`. The frontend macro hard-cut architecture test rejects restoring
`watchlistKindLabel(...)`.

## 2026-06-22 Continuation Note — Decision Console Severity Label Hard Cut

This continuation removes decision-console severity display inference from the
frontend workbench model. `macroWorkbenchModel.ts` now consumes only explicit
backend `severity_label` fields for confirmations, contradictions, top changes,
quality blockers, future catalysts, and watchlist rules; it no longer translates
severity codes such as `high` or `error` into operator-facing labels.

`macro_module_views.py` now emits `severity_label` for compacted quality
blockers, module evidence rows, and compacted top-change rows with severity.
Rows that omit `severity_label` in the browser can still render their explicit
non-severity metadata, but severity text is not manufactured in React.

## 2026-06-22 Continuation Note — Decision Console Section Label Hard Cut

This continuation removes decision-console section display inference from the
frontend workbench model. `macroWorkbenchModel.ts` now consumes only explicit
backend `node_label` fields for decision-console section meta; it no longer
rewrites node or kind codes such as `funding`, `rates`, or `trigger` into
operator-facing labels.

`macro_module_views.py` now keeps `node` as the stable node code and emits
`node_label` beside it for compacted top changes and module evidence rows.
Rows that omit `node_label` may still render their other explicit metadata, but
section text is not manufactured in React and raw node codes are not leaked.

## 2026-06-22 Continuation Note — Trade Map Outcome Label Hard Cut

This continuation removes Trade Map historical outcome display inference from
the frontend workbench model. `macroWorkbenchModel.ts` now requires explicit
backend `outcome_label` values for historical review rows; it no longer
translates `outcome` codes such as `hit` or `miss` into `命中` / `未中`.

`macro_module_views.py` now emits `outcome_label` beside the stable `outcome`
code for generated historical review rows. Historical rows that omit
`outcome_label` are dropped by the frontend instead of manufacturing outcome
copy in React.

## 2026-06-22 Continuation Note — Rates Workbench Concept And Gap Label Hard Cut

This continuation removes local Rates Workbench code-label maps from the
frontend model. `macroRatesWorkbenchModel.ts` no longer keeps
`CONCEPT_LABELS`, `humanizeRatesConceptKey(...)`, or `GAP_LABELS`; missing
primary items now come only from explicit backend data-gap labels, not
`missing_concept_keys` concept ids.

Rates gap rows whose label is only the raw gap code are omitted from display
coverage and missing-primary text. Stable keys may still carry the code, but
operator-facing copy must be supplied by the backend payload.

## 2026-06-22 Continuation Note — Macro Page Status Code Label Hard Cut

This continuation removes the remaining macro page status-code display map from
the frontend page view model. `macroPageViewModel.ts` now reads
`snapshot.status_label` as the only operator-facing module status label; it no
longer translates `snapshot.status` codes such as `ok`, `partial`, or
`insufficient_history` into Chinese labels.

`formatMacroScalar(...)` also leaves status-like scalar strings unchanged
instead of passing them through the old `STATUS_LABELS` map. Missing backend
display copy is therefore visible as missing or raw contract data during QA,
rather than being polished by browser compatibility code.

## 2026-06-22 Continuation Note — Source Table Status Code Label Hard Cut

This continuation removes local status-code display mapping from the macro
source metadata table. `MacroSourceTable` now uses only explicit
`status_label` fields when constructing the `新鲜度/质量/状态` cell; it no longer
translates `status` codes such as `ok`, `partial`, `success`, or `unavailable`
into operator-facing Chinese labels.

Rows with only a source label and a naked status code now disappear unless they
also contain another explicit audit cell such as freshness, quality, latest
observation date, concept count, score participation, or notes. This keeps
source health visible only when the backend has supplied display-ready evidence.

## 2026-06-22 Continuation Note — Source Table Provider Code Label Hard Cut

This continuation removes local provider-code display mapping from
`MacroSourceTable`. The table now accepts `source_label` only when it is already
display-ready text; raw lowercase provider ids such as `fred`, `yahoo`, `cboe`,
or `cex_market_intel` are treated as internal codes and the row is omitted.

The same rule applies to notes and degraded reasons through `displayText(...)`:
the frontend no longer rewrites provider ids or degradation ids into polished
operator copy. Backend macro provenance must own source display labels.

## 2026-06-22 Continuation Note — Table Scalar Status Code Label Hard Cut

This continuation removes the generic table scalar status-code display map from
`macroTableColumns.ts`. `formatMacroTableValue(...)` now formats numbers,
booleans, arrays, display cells, and empty sentinels, but it no longer
translates string values such as `ok`, `partial`, `degraded`, `missing`, or
`unavailable` into Chinese labels.

If a backend table cell intends to show a status label, it must provide that
label as `display_value`; otherwise the raw scalar remains visible in tests and
QA instead of being polished by a browser-side compatibility map.

## 2026-06-22 Continuation Note — Market Board Chart Status Fallback Hard Cut

This continuation removes the primary market-board chart status fallback from
`MacroMarketBoard.tsx`. Panel meta now renders only explicit
`chart.status_label`; it no longer exposes raw chart `status` codes such as
`partial` beside the panel title.

The market board may still render when a supporting table is present, but chart
status display is now owned by the backend payload. Missing chart copy remains
absent instead of becoming a raw status-code badge in the browser.

## 2026-06-22 Continuation Note — Rates Readiness Label Hard Cut

This continuation removes the Rates Workbench readiness-code display map from
`macroRatesWorkbenchModel.ts`. Rates readiness remains a logic enum derived from
`data_health.summary_status`, but the user-facing `readinessLabel` and
diagnostics module health label now come only from explicit
`data_health.summary_label`.

`RatesMarketRead` now omits the `状态` field entirely when that explicit label
is absent, rather than rendering an empty status row or manufacturing labels
such as `可用`, `部分可用`, `已过期`, or `缺失` in React.

## 2026-06-22 Continuation Note — Rates Diagnostics Severity Label Hard Cut

This continuation removes the Rates diagnostics gap severity/scope label maps
from `RatesDiagnosticsPanel`. Gap severity codes may still be present as
`data-severity` for styling, but the frontend no longer translates codes such
as `warning`, `info`, `critical`, `module_blocker`, or `chart_blocker` into
operator-facing text.

Rates diagnostic gap rows now render only explicit backend gap labels and
details. If a severity or scope needs to be displayed as text, that label must
come from the backend payload rather than a React-side map.

## 2026-06-22 Continuation Note — Rates Fact Quality Fallback Hard Cut

This continuation removes the Rates fact quality-code fallback from
`macroRatesWorkbenchModel.ts`. Fact status text now uses only explicit
`tile.quality_label`; raw `tile.quality` codes such as `partial` no longer
become user-facing status labels in the Rates fact strip.

The fact can still render its concept key, label, value, source, observed time,
and interpretation when those display-ready fields exist. Missing quality label
now leaves fact status blank instead of exposing a raw backend code.

## 2026-06-22 Continuation Note — Asset Daily Brief Stance Label Hard Cut

This continuation removes the Asset Daily Brief stance-code label map from
`AssetDailyBrief`. Daily-brief signal rows now render stance text only when the
backend has already supplied display-ready text; raw codes such as `supported`,
`risk`, `watch`, `mixed`, or `neutral` are treated as internal codes and omitted
from the signal row.

The daily brief still renders explicit headline and signal titles/bodies. If a
stance label should appear in the UI, it must be supplied by the backend as
display copy rather than inferred from a code substring in React.

## 2026-06-22 Continuation Note — Asset Diagnostics Severity Label Hard Cut

This continuation removes the asset diagnostics gap severity/scope label maps
from `AssetDiagnosticsBoard`. Gap severity may still be used as a styling
attribute, but React no longer translates internal codes such as `warning`,
`info`, `module_blocker`, or `chart_blocker` into operator-facing text.

Asset diagnostics now render only explicit backend gap labels and details. If a
severity or scope needs to be visible as text, it must be supplied as display
copy by the backend macro payload.

## 2026-06-22 Continuation Note — Asset Daily Brief Quality Placeholder Hard Cut

This continuation removes browser-side `样本不足` placeholders from
`AssetDailyBrief` data-quality rows. The daily brief quality panel now renders
only quality metrics whose numeric values are present in the backend payload.

If latest coverage, history coverage, or gap count are missing, those individual
rows are omitted. If all three are missing, the entire quality panel is omitted
instead of manufacturing a sample-size conclusion in React.

## 2026-06-22 Continuation Note — Asset Market Raw Field Fallback Hard Cut

This continuation removes raw-row display fallbacks from
`macroAssetOverviewModel`. Asset market rows now require symbol and date display
values to come from table cells, not from compatibility fields such as
`row.raw.symbol`, `row.raw.ticker`, `row.raw.latest_observed_at`, or
`row.raw.observed_at`.

Rows without a display-ready symbol cell are dropped. Rows without a
display-ready date cell keep `asOf` absent instead of exposing raw row dates.

## 2026-06-22 Continuation Note — Macro Diagnostics Severity Label Hard Cut

This continuation removes the overview/workbench data-health severity/scope
label maps from `MacroDiagnosticsPanel`. The shared macro diagnostics panel no
longer translates internal codes such as `warning`, `info`,
`module_blocker`, or `chart_blocker` into operator-facing text.

Macro diagnostics still render explicit backend gap labels and details, and
gap severity remains available as `data-severity` for styling. If severity or
scope needs to be visible as copy, the backend payload must provide that copy.

## 2026-06-22 Continuation Note — Macro Chart State Placeholder Hard Cut

This continuation removes the browser-side `历史样本不足` placeholder from
`MacroTimeSeriesChart`. Time-series charts may still show an insufficient
history state, but only when the backend has supplied an explicit chart or
series `status_label`.

If a chart has no drawable series and no explicit status label, the chart chrome
is omitted instead of fabricating a historical-sample conclusion from
`status: "insufficient_history"`.

## 2026-06-22 Continuation Note — Macro Correlation Placeholder Hard Cut

This continuation removes browser-side `-` placeholders from the macro
correlation model and tables. Missing correlation values now render as empty
cells, and pair metadata now shows only the explicit sample count plus an
explicit backend date range when both dates exist.

Correlation labels still render numeric backend correlations and source-backed
asset names. The frontend no longer fabricates missing correlation labels or
date ranges such as `- 至 -`.

## 2026-06-22 Continuation Note — Macro Market Event Flow Date Meta Fallback Hard Cut

This continuation removes the market-event flow date-as-meta fallback from
`MacroMarketEventFlowPanel`. Event rows now render the small meta label only
when the backend supplies explicit display-ready `meta` text.

The event `date` remains available as row data, but React no longer uses it as
a compatibility label when `meta` is absent. Missing meta now stays absent
instead of turning into a visible event date.

## 2026-06-22 Continuation Note — Rates Fact Observed-Date Fallback Hard Cut

This continuation removes the Rates fact raw observed-date display fallback
from `macroRatesWorkbenchModel.ts`. Fact dates now render only when the backend
supplies explicit display-ready `observed_at_label` text.

The raw `observed_at` field may still exist on the tile as source data, but it
is no longer used as browser-facing copy. Missing observed-date labels now stay
absent instead of exposing raw date strings in the Rates fact strip.

## 2026-06-22 Continuation Note — Source Table Observed-Timestamp Fallback Hard Cut

This continuation removes the source-table `observed_at_ms` browser formatting
fallback from `MacroSourceTable`. Source rows may still display an explicit
backend `latest_observed_at` value, but React no longer turns raw timestamp
milliseconds into a visible `最新观测` date.

Rows that only have raw `observed_at_ms` now omit the latest-observation column
instead of manufacturing a date label in the browser.

## 2026-06-22 Continuation Note — Macro Snapshot As-Of Date Fallback Hard Cut

This continuation removes browser-side as-of date display fallbacks from
`macroPageViewModel.ts` and `macroWorkbenchModel.ts`. Macro page headers,
freshness alerts, and workbench briefs now use only explicit backend
`snapshot.asof_label` copy for visible as-of text.

The raw `snapshot.asof_date` field may still exist as structured snapshot data,
but React no longer formats it into `截至 ...` or exposes the raw date as a
brief label when display-ready copy is absent.

## 2026-06-22 Continuation Note — Source Table Message Notes Fallback Hard Cut

This continuation removes the source-table raw `message` display fallback from
`MacroSourceTable`. Source table notes now render only explicit backend `notes`
or display-ready degraded-reason labels.

The raw `message` field may still exist in provider/source-health payloads, but
React no longer treats it as a browser-facing `备注` value.

## 2026-06-22 Continuation Note — Data Credibility Observed-Date Fallback Hard Cut

This continuation removes the decision-console data-credibility raw
`observed_at` display fallback from `macroWorkbenchModel.ts`. Data-credibility
rows now render an as-of value only when the backend supplies explicit
`observed_at_label` copy.

The raw `observed_at` field may still exist as structured observation data, but
React no longer exposes it as the user-facing data-credibility date.

## 2026-06-22 Continuation Note — Asset Overview Raw Meta Fallback Hard Cut

This continuation removes raw date/window meta fallbacks from
`MacroAssetOverviewPage`. The core asset market header now renders an as-of
label only from explicit backend `snapshot.asof_label`, and the 60-day
correlation header no longer formats correlation `asof_date` or `window` into
browser-facing meta copy.

The raw fields remain structured payload data, but the asset overview page no
longer manufactures visible `截至 ...`, `60d`, or generic correlation meta from
them.

## 2026-06-22 Continuation Note — Metric Tile Raw Value Fallback Hard Cut

This continuation removes the generic macro module metric-tile raw value
fallback from `macroModulePresentation.ts`. Key metric tiles now render a value
only when the backend supplies explicit display-ready `display_value` copy.

The raw `value` field may still exist as structured numeric source data, but
React no longer formats it into the user-facing `关键指标` strip. Tiles without
display-ready values are omitted, making missing backend presentation data
visible during QA instead of polished by frontend compatibility code.

## 2026-06-22 Continuation Note — Rates Fact Raw Value Fallback Hard Cut

This continuation removes the Rates Workbench fact raw value fallback from
`macroRatesWorkbenchModel.ts`. Rates facts now render a value only when the
backend supplies explicit display-ready `display_value` copy.

The raw `value` field may still exist as structured numeric fact data, but
React no longer formats it into the Rates fact strip. Facts without
display-ready values are omitted instead of exposing raw rates, spreads, or
provider numbers as polished operator copy.

## 2026-06-22 Continuation Note — Future Catalyst Window Fallback Hard Cut

This continuation removes the decision-console future-catalyst raw window
fallback from `macroWorkbenchModel.ts`. Future catalyst meta now uses only
explicit backend `window_label` copy for browser-facing time-window text.

The raw `window` field may still exist as structured catalyst data, but React
no longer promotes it into the `未来 24/72h 催化剂` meta line. If a time window
should be visible to operators, the backend must publish it as display-ready
`window_label`.

## 2026-06-22 Continuation Note — Watchlist Rule Window Label Contract Hard Cut

This continuation moves watchlist-rule time-window display ownership to the
backend. `macro_module_views.py` now publishes `window_label` alongside the
structured `window` for watchlist rules derived from scenario time windows.

`macroWorkbenchModel.ts` now renders watchlist rule meta using only explicit
`window_label`. Raw `window` remains structured data for sorting/audit, but it
no longer appears as browser-facing `Watchlist 与触发提醒` copy.

## 2026-06-22 Continuation Note — Market Event Flow Window Label Contract Hard Cut

This continuation moves market-event-flow time-window display ownership to the
backend. `macro_module_views.py` now publishes `window_label` for official
calendar, Treasury auction, Fed text, auction result, and news event-flow rows.

`macroWorkbenchModel.ts` now renders Market Event Flow meta using only explicit
`window_label`. Raw `window` remains structured classification data for sorting
and audit, but it no longer appears as browser-facing `市场事件流` copy.

## 2026-06-22 Continuation Note — Market Board Source Description Fallback Hard Cut

This continuation removes the market-board table source description-as-note
fallback from `MacroMarketBoard.tsx`. Table source notes now render only when
the backend supplies explicit `source.notes`.

`source.description` may still exist as structured provenance/context data, but
React no longer promotes it into a visible table note. Operator-facing source
remarks must be published as `notes`.

## 2026-06-22 Continuation Note — Macro Field-Key Label Fallback Hard Cut

This continuation removes the shared macro field-key display fallback from
`macroPageViewModel.ts`. `macroFieldLabel(...)` now returns explicit labels for
known v3 read fields and canonical concept keys only.

Unknown backend field keys now return `null` instead of being surfaced as
operator-facing copy. Any new field that should be visible must be explicitly
added to the display-label contract.

## 2026-06-22 Continuation Note — Decision Evidence Label Contract Hard Cut

This continuation moves decision-console evidence detail display ownership to the
backend. `macro_module_views.py` now emits `evidence_label` for module evidence
and overview top-change rows, and drops scenario evidence rows that only provide
legacy `description` copy.

`macroWorkbenchModel.ts` now renders confirmations, contradictions, and top
changes using only explicit `evidence_label`. Raw `description` remains valid for
other contracts such as quality blockers, watchlist rules, and future catalysts,
but it no longer acts as a decision-evidence display fallback.

## 2026-06-22 Continuation Note — Structured Analysis Evidence Label Hard Cut

This continuation aligns structured market analysis with the decision-console
evidence contract. `_structured_signal_line(...)` now requires explicit
`evidence_label`; it no longer falls back to `change_label`, `value_label`, or a
bare signal label when building structured-analysis market evidence.

`change_label` and `value_label` may remain structured payload fields for other
readers, but they no longer independently create operator-facing market evidence
copy without the canonical `evidence_label`.

## 2026-06-22 Continuation Note — Macro Table Object Display Fallback Hard Cut

This continuation removes the generic macro table object `label`/`title`
display fallback from `macroTableColumns.ts`. Object-shaped table cells now
render only when the backend supplies explicit `display_value`.

Backend `label` and `title` fields may still exist as structured metadata on
other payloads, but macro table cells no longer promote them into visible table
copy without the canonical display-cell contract.

## 2026-06-22 Continuation Note — Decision-Console Time Window Label Contract Hard Cut

This continuation removes raw decision-console `time_window` display fallbacks
from `macroWorkbenchModel.ts`. Scenario case meta, module-evidence meta, and
trade-map window copy now render only from explicit backend
`time_window_label`.

Backend `time_window` remains structured horizon data for audit and downstream
logic, but it no longer becomes operator-facing browser copy. The macro
scenario generator now emits display-ready labels for generated scenario cases
and trade maps, and module evidence preserves `time_window_label` only when the
backend provides it explicitly.

## 2026-06-22 Continuation Note — Data-Health Gap Description Fallback Hard Cut

This continuation removes the data-health gap `description` detail fallback from
`macroModulePresentation.ts`. Data-health gap detail now renders only from
actionable `remediation_hint` or an explicit `detail` field.

Backend `description` may remain structured context, but React no longer turns a
description-only gap into operator-facing remediation copy. Missing remediation
now stays visibly missing instead of being polished into a pseudo-action item.

## 2026-06-22 Continuation Note — Module Evidence Label Contract Hard Cut

This continuation aligns leaf-module driver evidence with the decision-console
evidence contract. `macroModulePresentation.ts` now renders module evidence
details only from explicit backend `evidence_label`.

Backend `description` may remain structured context on module evidence rows,
but React no longer uses it as the visible `驱动与反证` evidence detail. Rows
without a display-ready evidence label are dropped from the evidence group
instead of being polished into operator-facing copy.

## 2026-06-22 Continuation Note — Rates Decision Evidence Label Contract Hard Cut

This continuation applies the same evidence-label contract to the Rates
Workbench `决策支持` panel. `macroRatesWorkbenchModel.ts` now renders decision
item detail only from explicit backend `evidence_label`.

Backend `description` may remain structured context on rates module-evidence
rows, but it no longer becomes visible decision-support detail. Rates decision
rows can remain label-only when no display-ready evidence detail is provided.

## 2026-06-22 Continuation Note — Metric Tile Observed-At Label Contract Hard Cut

This continuation removes metric tile quality/delta label fallbacks from
`macroModulePresentation.ts`. Module metric cards now render `observedAtLabel`
only from explicit backend `observed_at_label`.

Backend `quality_label` and `delta_label` remain valid metric metadata, but they
no longer become browser-facing observed-at copy. Missing observation labels now
stay missing instead of being disguised as data quality or change text.

## 2026-06-22 Continuation Note — Rates Fact Interpretation Contract Hard Cut

This continuation removes the Rates fact `delta_label` interpretation fallback
from `macroRatesWorkbenchModel.ts`. Rates fact interpretation now renders only
when the backend supplies explicit `description` copy.

Backend `delta_label` remains valid change metadata, but it no longer becomes
browser-facing explanatory copy. A Rates fact without interpretation now stays
label/value-only instead of turning a raw movement label into analysis.

## 2026-06-22 Continuation Note — Generic Object Scalar Display Contract Hard Cut

This continuation removes generic object `label`/`title` display fallbacks from
`macroPageViewModel.ts`. `formatMacroScalar(...)` now renders object values only
when the backend supplies explicit `display_value`.

Data-health gap labels remain allowed from explicit `display_value` or `label`,
but gap-only `title` no longer becomes browser-facing copy. This keeps generic
formatting helpers from manufacturing useful-looking macro text out of
structural object metadata.

## 2026-06-22 Continuation Note — Macro Chart Series Title Label Hard Cut

This continuation removes chart series `title` display fallbacks from
`macroChartModel.ts`. Chart and heatmap series labels now render only from
explicit `label` or `short_label`.

Backend `title` remains valid chart/object metadata, but it no longer becomes a
series label. Title-only series or heatmap rows now drop from chart models
instead of appearing as source-backed indicators.

## 2026-06-22 Continuation Note — Watchlist Asset Symbol Label Hard Cut

This continuation removes the Watchlist asset `symbol` display-label fallback
from `macroWorkbenchModel.ts`. Watchlist assets now enter the decision-console
view model only when the backend supplies an explicit asset `label`.

Backend `symbol` remains valid structured asset metadata, but it no longer
becomes the browser-facing asset label. Symbol-only watchlist rows now drop
from the visible model instead of masquerading as researched asset names.

## 2026-06-22 Continuation Note — Workbench Brief Raw Regime Hard Cut

This continuation removes raw `module_read.regime` from the Workbench brief
field list in `macroWorkbenchModel.ts`. Brief status rows now render only from
explicit backend `regime_label`.

Backend `regime` remains valid structured regime identity for audit and model
logic, but it no longer becomes browser-facing “状态” copy when no display label
is available.

## 2026-06-22 Continuation Note — Decision-Console Code Identity Hard Cut

This continuation removes `code` as a row-identity fallback for future
catalysts and Watchlist rules in `macroWorkbenchModel.ts`. Those decision
console rows now require explicit backend `key` fields before they enter the
visible view model.

Backend `code` may remain structured classifier metadata on other records, but
it no longer becomes a product row identity for future-catalyst or Watchlist
rule display.

## 2026-06-22 Continuation Note — Module Evidence Key Identity Hard Cut

This continuation removes `key` as an identity fallback for leaf-module
evidence rows in `macroModulePresentation.ts`. Module evidence items now enter
the `驱动与反证` model only when the backend supplies explicit `code`.

Backend `key` may remain structured metadata on other macro records, but it no
longer backfills module-evidence row identity for visible driver evidence.

## 2026-06-22 Continuation Note — Rates Chart Note Status Label Hard Cut

This continuation removes `primary_chart.status_label` as a chart-note fallback
from `macroRatesWorkbenchModel.ts`. Rates chart notes now render only from
explicit backend `primary_chart.subtitle`.

Backend chart status labels may remain structured readiness metadata, but they
no longer become browser-facing explanatory chart-note copy.

## 2026-06-22 Continuation Note — Data-Health Gap Generic Detail Hard Cut

This continuation removes generic data-health `detail` as an actionable
remediation fallback from `macroModulePresentation.ts`. Macro data-health gap
detail now renders only from explicit backend `remediation_hint`.

Backend `detail` may remain structured gap metadata, but it no longer becomes
browser-facing remediation copy when the backend has not supplied a dedicated
remediation hint.

## 2026-06-22 Continuation Note — Macro Chart Inline Points Hard Cut

This continuation removes v2 inline chart-point fallbacks from
`macroChartModel.ts`. Time-series charts now draw only from hydrated
module-adjacent series payloads, and yield-curve values now require explicit
`latest`/`latest_value`/`value` fields.

Backend inline `series.points` may remain legacy metadata during transition,
but it no longer becomes drawable chart data or inferred yield-curve latest
values in the browser.

## 2026-06-22 Continuation Note — Rates Corridor Inline Points Hard Cut

This continuation removes the matching v2 inline chart-point fallback from
`macroRatesChartModel.ts`. Fed funds corridor charts now require hydrated
module-adjacent series payload points before rendering target bounds or market
rate lines.

Backend inline `series.points` may remain legacy metadata during transition,
but it no longer becomes drawable Rates corridor data or inferred latest
values in the browser.

## 2026-06-22 Continuation Note — Asset Market Daily Delta Hard Cut

This continuation removes the asset-market `delta_20d` fallback from
`macroAssetOverviewModel.ts`. Asset market rows now render daily-change copy and
tone only from explicit `delta_1d` table cells.

Backend `delta_20d` may remain long-window momentum metadata, but it no longer
masquerades as a latest daily change when `delta_1d` is missing.

## 2026-06-22 Continuation Note — Asset Market Generic Date Hard Cut

This continuation removes generic asset-market `date` and `asof_date` display
fallbacks from `macroAssetOverviewModel.ts`. Asset market row observation labels
now render only from explicit `observed_at` or `latest_observed_at` table cells.

Backend `date` and `asof_date` may remain generic table metadata, but they no
longer masquerade as latest-observation labels in the browser.

## 2026-06-22 Continuation Note — Asset Market Daily Header Hard Cut

This continuation removes the stale `20日变化` asset-market table header from
`AssetMarketDashboard.tsx`. The retained asset board now labels the visible
`delta_1d` column as `日涨跌幅`.

Backend long-window momentum fields may remain explicit table metadata, but the
browser no longer labels the current daily-change column as a 20-day change.

## 2026-06-22 Continuation Note — Asset Market Source Quality Hard Cut

This continuation removes `source` as a quality-badge fallback from
`macroAssetOverviewModel.ts`. Asset market row badges now render only from
explicit `quality` table cells.

Backend source/provider cells may remain provenance metadata, but they no longer
masquerade as asset-row quality labels in the retained asset market board.

## 2026-06-22 Continuation Note — Macro Chart Visible Legend Hard Cut

This continuation removes non-drawable series from time-series chart legends in
`MacroTimeSeriesChart.tsx`. Chart legends now render only the same series that
are actually drawn on the chart canvas.

Under-minimum series may remain in the backend chart model for diagnostics, but
they no longer appear as visible legend rows or `n/a` placeholder values when no
line is drawn for them.

## 2026-06-22 Continuation Note — Macro Chart Payload Metadata Hard Cut

This continuation removes hydrated series payload `status`, `status_label`, and
`unit` as display-metadata fallbacks from `macroChartModel.ts`. Time-series
status labels and units now come only from explicit `primary_chart.series`
records.

Hydrated series payloads remain the source of drawable points, but they no
longer backfill chart legend units or chart state labels in the browser.

## 2026-06-22 Continuation Note — Macro Freshness Label Inference Hard Cut

This continuation removes Chinese display-label parsing from
`macroPageViewModel.ts` freshness alert detection. Page freshness alerts now
trigger only from explicit stale gap codes such as `stale_latest*` or `stale_*`.

Data-health labels remain display copy, but they no longer drive browser-side
freshness semantics by containing words such as `滞后`.

## 2026-06-22 Continuation Note — Rates Corridor Payload Metadata Hard Cut

This continuation removes hydrated payload metadata and old latest-value fields
as display fallbacks from `macroRatesChartModel.ts`. Rates corridor series now
derive drawable values only from hydrated payload points and derive display
units only from explicit `primary_chart.series` metadata.

Hydrated series payloads remain the source of drawable points, but they no
longer backfill corridor units or resurrect `latest_value` / `value` legacy
fields in the browser model.

## 2026-06-22 Continuation Note — Macro Chart Legacy Latest-Value Hard Cut

This continuation removes generic `latest_value` / `value` fallbacks from
`macroChartModel.ts` yield-curve point construction. Yield-curve charts now
require explicit `primary_chart.series.latest` for current point values.

Legacy numeric fields may remain in old backend payloads during transition, but
they no longer make a missing-current-contract yield-curve point appear
renderable in the browser.

## 2026-06-22 Continuation Note — Macro Chart Payload Point-Count Hard Cut

This continuation removes the hydrated payload-length fallback from
`macroChartModel.ts` chart point-count metadata. Time-series chart models now
expose `pointCount` only when the backend supplies explicit
`primary_chart.series.point_count`.

Hydrated series payloads remain the source of drawable chart points, but their
array length no longer masquerades as backend-declared history coverage in the
browser model.

## 2026-06-22 Continuation Note — Rates Gap Display-Value Label Hard Cut

This continuation removes `display_value` as a Rates data-health gap label
fallback from `macroRatesWorkbenchModel.ts`. Rates gap summaries now enter the
diagnostics model only when the backend supplies explicit `gap.label` plus a
valid gap code and severity.

Backend `display_value` may remain structured table or scalar metadata, but it
no longer masquerades as a source-health repair label in the Rates workbench.

## 2026-06-22 Continuation Note — Rates Curve History Summary Hard Cut

This continuation removes point-derived summary metadata from
`macroRatesWorkbenchModel.ts` curve spread histories. Rates curve history cards
now enter the diagnostics model only when the backend supplies explicit
`latest_bp`, `min_bp`, and `max_bp` alongside valid history points.

History points remain drawable evidence for sparkbars, but their values no
longer backfill browser-facing latest/range summary copy when the backend has
not declared that summary metadata.

## 2026-06-22 Continuation Note — Macro Table Display-Cell Raw Value Hard Cut

This continuation removes `display_value` as a raw/sort fallback for macro table
display cells in `macroTableColumns.ts`. Display cells still render explicit
`display_value` copy, but `rawValue` and `sortValue` now come only from explicit
backend `sort_value` metadata.

Backend display copy may remain human-facing table text, but it no longer
masquerades as browser raw or sortable semantics when the backend has not
declared those semantics.

## 2026-06-22 Continuation Note — Macro Route Descriptor Default Hard Cut

This continuation removes parser-local route metadata defaults from
`macroRoutes.ts`. The empty `/macro` tail now resolves only when the explicit
`overview` descriptor exists in the macro route registry, and the returned
`pageKind`, `productTier`, `routeId`, and canonical path all come from that
descriptor.

The route parser no longer keeps `overview` / `primary` defaults as a
compatibility branch if the registry contract is broken.

## 2026-06-22 Continuation Note — Market Board Default Title Hard Cut

This continuation removes the frontend `市场板` default title from
`MacroMarketBoard.tsx`. Market-board chrome now renders only when the caller
passes an explicit panel title, while retained overview and leaf pages continue
to pass their source-backed board titles directly.

The market board no longer manufactures generic evidence-panel copy when an
upstream caller omits the title contract.

## 2026-06-22 Continuation Note — Data-Health Gap Display-Value Label Hard Cut

This continuation removes `display_value` as a generic data-health gap label
fallback from `macroPageViewModel.ts`. Macro gap labels now require explicit
backend `label` metadata; `display_value` remains scalar/table display copy and
cannot masquerade as a repair or freshness label.

The shared gap helper now matches the Rates-specific hard cut: unlabeled gaps
drop out of the frontend instead of becoming operator-facing data-quality rows.

## 2026-06-22 Continuation Note — Macro Module Title Route-Label Hard Cut

This continuation removes `macroRouteLabel(...)` as a module-title fallback from
`macroPageViewModel.ts` and `MacroWorkbenchRoute.tsx`. Macro shell titles now
require explicit backend `snapshot.title` metadata; when a module payload lacks
that title, the route surfaces a contract error instead of rendering a route
label as if the module were healthy.

Route labels remain navigation labels only. They no longer masquerade as
backend module-title metadata or hide a broken `macro_module_view_v3` snapshot
contract from the operator.

## 2026-06-22 Continuation Note — Macro Leaf Page Route-Label Metadata Hard Cut

This continuation removes `macroRouteLabel(moduleId)` from
`MacroLeafModulePage.tsx` page-region labels and driver-board metadata. Leaf
module page chrome now derives those labels from explicit backend
`snapshot.title` text, matching the macro shell title contract.

Navigation labels remain short navigation affordances only. They no longer
masquerade as module page metadata or driver context when the backend has
already declared the product-facing module title.

## 2026-06-22 Continuation Note — Macro Overview And Assets Static Page Metadata Hard Cut

This continuation removes static page-region labels from
`MacroOverviewModulePage.tsx` and `MacroAssetOverviewPage.tsx`, plus the static
`总览` driver-board meta from the overview page. Overview and assets landing
page chrome now derive module page labels and overview driver context from
explicit backend `snapshot.title` text.

The overview and assets landing pages now follow the same no-synthetic-title
contract as leaf pages: if the backend does not supply displayable
`snapshot.title` metadata, the page does not manufacture module chrome from
route names or hard-coded Chinese labels.

## 2026-06-22 Continuation Note — Macro Shell Header Question Wiring Hard Cut

This continuation removes the unused `question` field from
`MacroShellHeaderModel` and deletes all route-shell assignments that passed
`snapshot.question` or `snapshot.subtitle` into that dead header field.

Macro module read models may still carry explicit research questions where
their owning pages consume them. The route shell no longer preserves an unused
question channel, and `snapshot.subtitle` can no longer masquerade as header
question metadata.

## 2026-06-22 Continuation Note — Rates Workbench Question Wiring Hard Cut

This continuation removes the unused `question` field from
`RatesWorkbenchView` and deletes frontend hard-coded Rates question copy from
`RATES_PAGE_COPY`.

Rates page titles remain as compact local page chrome, but prompt-style
research questions must come from a backend field that an owning UI actually
renders. The rates workbench no longer carries dead question metadata or
fallback copy that can imply a source-backed research question when none is
being consumed.

## 2026-06-22 Continuation Note — Rates Workbench Title Page-Copy Hard Cut

This continuation removes the remaining frontend `RATES_PAGE_COPY` title
fallback from `macroRatesWorkbenchModel.ts`. Rates workbench titles now read
only explicit backend `snapshot.title` metadata.

If a Rates module lacks displayable title metadata, the Rates page returns no
scaffold instead of manufacturing local titles such as `联邦基金与走廊`,
`收益率曲线`, or `实际利率`. This aligns the Rates workbench with the macro
shell, leaf page, overview page, and asset landing no-synthetic-title contract.

## 2026-06-22 Continuation Note — Macro Shell Eyebrow Fallback Hard Cut

This continuation removes `宏观工作台` as a route-shell eyebrow fallback from
`MacroWorkbenchRoute.tsx`. Generic macro module headers now render eyebrow
copy only when the backend supplies explicit `snapshot.section` metadata.

The shell header model now treats `eyebrow` as optional, and
`MacroPageHeader` omits the kicker element when no displayable eyebrow exists.
This prevents missing section metadata from looking like a source-backed module
classification.

## 2026-06-22 Continuation Note — Macro Shell Local Eyebrow Copy Hard Cut

This continuation extends the eyebrow hard cut to the assets and rates branches
in `MacroWorkbenchRoute.tsx`. The route shell no longer supplies local
`Assets` or `利率工作台` kicker copy.

All macro shell eyebrow copy now flows through the same
`macroModuleSection(module)` helper, so the shell can only display module
classification text when the backend supplies explicit `snapshot.section`
metadata.

## 2026-06-22 Continuation Note — Rates Scaffold Label Hard Cut

This continuation removes the Rates-only `${title}利率工作台` page-scaffold
label from `MacroRatesModulePage.tsx`. Rates pages now use the same
`${title}模块页面` scaffold label pattern as overview, assets, and leaf module
pages.

The Rates page scaffold remains derived from backend `snapshot.title`, but no
longer appends a local workbench label that makes Rates pages look like a
separate compatibility shell.

## 2026-06-22 Continuation Note — Rates Primary Chart Meta Hard Cut

This continuation removes `view.readinessLabel` as a Rates primary-chart panel
meta fallback from `RatesPrimaryVisual.tsx`. The chart panel header now shows
only explicit backend chart copy from `primary_chart.subtitle`; module readiness
stays in the Rates brief and diagnostics surfaces where it belongs.

This prevents page-level readiness copy such as `走廊数据部分可用` from
masquerading as chart-specific evidence when the backend has not supplied chart
subtitle metadata.

## 2026-06-22 Continuation Note — Rates Market Read Eyebrow Hard Cut

This continuation removes the Rates market-read module-title eyebrow from
`RatesMarketRead.tsx` and deletes the now-unused `.macro-rates-eyebrow` CSS
rule. The module title remains owned by the page scaffold and route shell; the
brief no longer repeats `snapshot.title` as local kicker copy.

The Rates brief is now a decision read: headline, readiness/as-of state, gap
count, and explicit missing-primary details. It no longer adds a second local
title layer inside the same page.

## 2026-06-22 Continuation Note — Macro Diagnostics Header Meta Hard Cut

This continuation removes `diagnostics.sourceMeta` as a header meta fallback
from `MacroDiagnosticsPanel.tsx`. Source counts remain visible inside the
diagnostic summary and source table disclosure, but they no longer appear in the
panel header when the backend has not supplied a data-health status label.

The diagnostics panel header now communicates only explicit status metadata,
not local source-count bookkeeping.

## 2026-06-22 Continuation Note — Decision Evidence Node-Label Meta Hard Cut

This continuation removes `node_label` as a `module_evidence` meta fallback
from `macroWorkbenchModel.ts`. Confirmation and contradiction meta now renders
only explicit backend `meta`, `time_window_label`, and `severity_label`
metadata.

Top-change node labels remain owned by the structured decision-console
`top_changes` model. Generic module evidence no longer turns old node-label
context into decision evidence meta when the backend has not supplied a
display-ready meta field.

## 2026-06-22 Continuation Note — Macro Chart Series-State Fallback Hard Cut

This continuation removes child-series `status_label` as a parent chart state
fallback from `MacroTimeSeriesChart.tsx`. A chart with no renderable series now
shows a state panel only when the backend supplies chart-level `status_label`.

Series-local status remains available to model diagnostics, but it no longer
masquerades as whole-chart status copy.

## 2026-06-22 Continuation Note — Decision Top-Change Source-Meta Hard Cut

This continuation removes `node_label` as decision-console `top_changes` meta
copy from `macroWorkbenchModel.ts`. Top-change meta now renders source-backed
change metadata from backend fields such as `change_label`, `value_label`,
`source_label`, `observed_at`, and `severity_label`.

Section labels remain backend display metadata, but they no longer occupy the
most valuable first-screen meta slot when concrete market-change evidence is
available. A top change without source-backed meta fields now renders no meta
instead of falling back to broad section labels such as `资金面` or
`跨资产确认`.

## 2026-06-22 Continuation Note — Macro Placeholder String Hard Cut

This continuation removes production frontend handling for the old `暂无`
placeholder value from macro scalar, table, asset market, and asset diagnostics
rendering. Macro frontend code now treats only actual empty values (`null`,
`undefined`, or blank strings) as absent.

Tests that previously fed `暂无` as an empty-value protocol now use blank or
null payload values. This keeps the UI omission behavior while deleting the
compatibility assumption that a Chinese placeholder string is part of the
`macro_module_view_v3` contract.

## 2026-06-22 Continuation Note — Rates Corridor Legend Placeholder Hard Cut

This continuation removes the Rates corridor chart legend `n/a` placeholder
from `RatesCorridorChart.tsx`. Corridor legend values now render only when the
model carries a real numeric latest value; missing latest values produce no
legend value text instead of a synthetic placeholder.

The corridor geometry and axis labels still use actual series points. This cut
only removes local display copy that made malformed or incomplete corridor
series look intentionally labelled.

## 2026-06-22 Continuation Note — Rates Corridor Series Label Hard Cut

This continuation removes the Rates corridor model's local series-label
fallback from `macroRatesChartModel.ts`. Renderable corridor series now require
the backend `primary_chart.series[].label` field; a known corridor concept with
hydrated points but no display label is treated as missing rather than being
labelled from a frontend concept map.

`CORRIDOR_LABELS` remains only for required/missing concept labels, where the
API still sends concept keys as gap identity. It no longer turns present series
into display-ready chart lines.

## 2026-06-22 Continuation Note — Macro Heatmap Missing-Cell Placeholder Hard Cut

This continuation removes the macro heatmap matrix `n/a` placeholder from
`macroChartModel.ts`. Missing correlation cells now preserve `rawValue: null`
for data state and render an empty display label instead of local placeholder
copy.

The heatmap still renders source-backed numeric correlations and row/column
labels from backend metadata. It no longer makes absent correlation values look
like intentional product text.

## 2026-06-22 Continuation Note — Module Read Regime Summary Fallback Hard Cut

This continuation removes `module_read.regime_label` as a module brief summary
fallback from `macroModulePresentation.ts`. Module briefs now require explicit
backend `module_read.headline` or `module_read.summary` copy before they render
a summary paragraph.

`regime_label` remains available as structured regime metadata in surfaces that
explicitly model it. It no longer masquerades as a source-backed read summary
when the backend has not supplied headline or summary text.

## 2026-06-22 Continuation Note — Macro Field-Key Label Map Hard Cut

This continuation removes the dead frontend `macroFieldLabel` export and
`FIELD_LABELS` map from `macroPageViewModel.ts`. The map had no production
callers and only preserved local field-key-to-copy translation in tests.

Macro field labels must now arrive as display-ready backend metadata on the
surface that renders them. The frontend no longer keeps a generic macro field
key label map that can turn raw read-model keys such as `regime_label` or
`confidence_label` into product copy.

## 2026-06-22 Continuation Note — Source Table Score Participation Label Hard Cut

This continuation removes the source-table `score_participation` boolean label
map from `MacroSourceTable.tsx`. The table no longer turns raw boolean audit
state into local product copy such as `参与计分` or `计分排除`.

Source audit rows still render explicit backend source labels, latest
observation labels, quality labels, concept counts, and notes. If scoring
participation needs user-facing copy, it must arrive as display-ready backend
metadata rather than a frontend boolean-to-copy compatibility path.

## 2026-06-22 Continuation Note — Source Table Degraded Reasons Notes Hard Cut

This continuation removes the source-table `degraded_reasons` notes fallback
from `MacroSourceTable.tsx`. Source-health reason arrays are no longer treated
as display-ready notes, even when they contain human-readable strings.

The source table now renders the remarks column only from explicit backend
`notes` text. Provider degradation reasons remain raw diagnostics unless the
backend projects a user-facing note field for this surface.

## 2026-06-22 Continuation Note — Asset Daily Brief Block Coercion Hard Cut

This continuation removes `String(...)` coercion from asset daily-brief block
normalization in `macroAssetOverviewModel.ts`. Brief block `id`, `title`, and
`body` now must be actual backend strings before the block can render.

The frontend no longer turns numbers or booleans into display copy such as
`123`, `456`, or `true`. Daily brief prose must remain explicit backend
metadata rather than a compatibility side effect of loose JavaScript coercion.

## 2026-06-22 Continuation Note — Macro Scalar Boolean Label Hard Cut

This continuation removes boolean handling from `formatMacroScalar(...)` and
from workbench brief value detection. The macro frontend no longer turns raw
boolean fields into local `是` / `否` display copy.

Numeric and string scalar display remains available, and object scalars still
require explicit `display_value`. Boolean read-model fields must be projected
as backend display metadata before they can appear in the macro workbench.

## 2026-06-22 Continuation Note — Decision Quality Blocker Description Hard Cut

This continuation removes `description` as the detail source for decision
console `quality_blockers`. Quality blockers now require explicit backend
`evidence_label` copy before they can render inside the first-screen decision
console.

This aligns quality blockers with confirmations, contradictions, and top
changes: generic `description` fields remain raw/legacy context unless the
backend projects display-ready evidence text for the specific decision surface.

## 2026-06-22 Continuation Note — Future Catalyst Detail Contract Hard Cut

This continuation removes the `description` display contract from overview
decision-console `future_catalysts`. Backend module views now emit each
short-window catalyst row with explicit `detail`, and the macro workbench model
requires `detail` before a catalyst can render.

Scenario source records may still carry internal descriptions, but the public
decision-console row no longer exposes or consumes `description` as
operator-facing copy. Description-only catalyst rows are dropped, and frontend
and backend hard-cut tests reject restoring the old field.

## 2026-06-22 Continuation Note — Watchlist Rule Detail Contract Hard Cut

This continuation removes the `description` display contract from
`decision_console.watchlist_alerts.rules`. Backend module views now emit each
watchlist rule row with explicit `detail`, and the macro workbench model
requires `detail` before a rule can render.

Scenario watch triggers and invalidations are consumed by the backend as
display-bearing signal records, while quality rules can use explicit evidence
or remediation metadata. The public Watchlist rule row no longer exposes or
consumes `description`, description-only frontend payloads are dropped, and
frontend/backend architecture guards reject restoring the old path.

## 2026-06-22 Continuation Note — Scenario Watch Detail Contract Hard Cut

This continuation moves scenario `watch_triggers` and `invalidations` onto an
explicit `detail` contract at the producer boundary. The scenario engine no
longer emits `description` for operator-facing watch and invalidation records.

Overview future catalysts and Watchlist rules now consume only scenario
`detail` for watch/invalidation display copy. Description-only scenario signal
rows are dropped from these decision-console surfaces instead of being promoted
into public operator text.

## 2026-06-22 Continuation Note — Event Catalyst Detail Source Hard Cut

This continuation moves macro event catalyst candidates onto explicit `detail`
at the producer boundary. `_event_catalyst(...)` no longer emits display
`description` for official calendar, Treasury auction, or Fed text events.

Future catalysts, market event flow rows, Fed communication structured analysis,
and scenario invalidation fallbacks now consume only explicit `detail` for
operator-facing copy. Description-only event catalyst rows are dropped instead
of being promoted into visible macro research text.

## 2026-06-22 Continuation Note — Quality Blocker Evidence Label Source Hard Cut

This continuation moves macro quality blockers onto explicit `evidence_label`
at the producer and backend module-view boundary. Scenario quality blockers no
longer emit display `description`, and decision-console quality blockers no
longer expose `description` as their public detail field.

Watchlist quality rules now consume only explicit `detail`, `evidence_label`,
or `remediation_hint`. Description-only quality blockers are omitted from
visible decision-console and Watchlist output instead of being promoted into
operator-facing remediation copy.

## 2026-06-22 Continuation Note — Backend Availability Placeholder Hard Cut

This continuation removes backend-generated placeholder cells from the macro
module availability table. Data-gap rows no longer synthesize `n/a` latest
values or `计分排除` coverage values when those fields are not source-backed.

The availability table also no longer creates a synthetic "no explicit gap"
row when there are no concepts or gaps to report. Empty availability evidence
now remains empty instead of being filled with local reassurance copy.

## 2026-06-22 Continuation Note — Missing Change Status Zero Hard Cut

This continuation removes the remaining backend status helpers that converted
missing short-window change history into `0.0` before assigning macro status.
Asset VIX rows, credit NFCI financial-conditions rows, and HYG/LQD relative
credit ETF rows now preserve missing trend history as `insufficient_history`
unless the current level alone crosses an explicit stress threshold.

The cut prevents `assets` and `credit/stress` diagnostics from presenting a
neutral, tightening, or relief read when the required change window is absent.
Missing history now stays visible as data quality instead of becoming a false
market conclusion.

## 2026-06-22 Continuation Note — Credit Spread Missing-History Stable Hard Cut

This continuation removes the backend credit-spread status branches that turned
missing 1w spread history into stable credit reads. Asset landing HY OAS rows,
credit-stress HY/IG OAS rows, and CCC-HY tail rows now emit
`insufficient_history` when the change window is absent.

Current spread levels still render as facts, but the public module view no
longer presents "信用稳定" or "稳定" when the read model lacks the historical
window needed to make that judgement.

## 2026-06-22 Continuation Note — Yield Curve Missing-History Stable Hard Cut

This continuation removes the backend yield-curve spread status branch that
turned a missing 1w spread-change window into a stable curve read. Positive
curve spreads without a usable change window now emit `insufficient_history`
instead of "稳定".

Current inversion still renders as a source-backed cross-sectional fact, but
the public yield-curve module view no longer presents stability when the read
model lacks the historical window needed to make that judgement.

## 2026-06-22 Continuation Note — Crypto Derivatives Missing-History Signal Hard Cut

This continuation removes backend crypto-derivatives status branches that
turned missing 1w OI or DVOL history into tradeable calm signals. Single-point
perp OI rows now emit `insufficient_history` instead of "杠杆平稳", and low
DVOL rows without a usable change window emit `insufficient_history` instead
of "波动回落".

Current high DVOL still renders as a source-backed hot-volatility fact, but the
public crypto module view no longer presents stable leverage or volatility
relief when the read model lacks the historical window needed to make that
judgement.

## 2026-06-22 Continuation Note — Real Rates Missing-History Stable Hard Cut

This continuation removes backend real-rates status branches that turned
missing 1w real-yield or breakeven history into stable reads. Sub-threshold
real-yield rows and breakeven rows without a usable change window now emit
`insufficient_history` instead of "稳定".

Current high real-yield levels still render as a source-backed valuation
pressure fact, but the public real-rates module view no longer presents stable
real-rate or inflation-compensation reads when the read model lacks the
historical window needed to make that judgement.

## 2026-06-22 Continuation Note — Inflation Breakeven Missing-History Stable Hard Cut

This continuation removes the backend inflation breakeven status branch that
turned missing 1m breakeven history into a stable inflation-expectations read.
Sub-threshold 10Y breakeven rows without a usable change window now emit
`insufficient_history` instead of "稳定".

Current 10Y breakeven levels at or above 2.5% still render as source-backed
expectation pressure, but the public inflation module view no longer presents
stable inflation-compensation reads when the read model lacks the historical
window needed to make that judgement.

## 2026-06-22 Continuation Note — Growth Missing-History Stable Hard Cut

This continuation removes backend growth row status branches that turned
missing GDP, GDPNow, industrial production, housing, PCE, or retail trend
windows into stable growth reads. Mid-range growth rows without the required
1q or 1m change window now emit `insufficient_history` instead of "稳定" or
"Nowcast 稳定".

Current values that cross explicit directional thresholds still render as
source-backed contraction, slowing, resilient, expanding, cooling, or housing
drag facts. The public GDP module view no longer presents stability when the
read model lacks the historical window needed to judge a stable trend.

## 2026-06-22 Continuation Note — Employment Missing-History Stable Hard Cut

This continuation removes backend employment row status branches that turned
missing unemployment, payroll, claims, openings, or wage trend windows into
stable labor reads. Mid-range employment rows without the required 1m change
window now emit `insufficient_history` instead of "稳定".

Current values that cross explicit labor-market thresholds still render as
source-backed deterioration, tight labor, slowing, strong payrolls, claims
stress, demand cooling/tightness, or wage pressure. The public employment
module view no longer presents labor stability when the read model lacks the
historical window needed to judge a stable trend.

## 2026-06-22 Continuation Note — TGA Missing-History Stable Hard Cut

This continuation removes the backend TGA row status branch that turned a
missing 1w Treasury cash-account change window into a stable liquidity read.
Sub-threshold TGA rows without a usable change window now emit
`insufficient_history` instead of "稳定".

Current high TGA levels still render as the source-backed `treasury_high`
fact, and RRP current-balance buffer facts remain unchanged. The public
liquidity module view no longer presents TGA stability when the read model
lacks the historical window needed to judge Treasury drain or injection.

## 2026-06-22 Continuation Note — Overview Scenario Contract Hard Cut

This continuation removes overview decision-console fallbacks that made a
malformed `scenario_json` look complete. The module view now requires
`scenario_cases` to be present, requires a real `base` case before building the
market-thesis row, and requires explicit `quality_blockers` from scenario
output instead of rebuilding them from `data_health.global_gaps`.

Empty `quality_blockers` is still a valid explicit scenario result. Missing
scenario fields or missing base-case planning now fail at the module-view
boundary, so the public `/macro` overview cannot silently replace broken
projection output with empty lists or a first-case guess.

## 2026-06-22 Continuation Note — Overview Scenario Signal List Hard Cut

This continuation extends the overview scenario contract to the remaining
display-driving list fields. `top_changes`, `trade_map`, `watch_triggers`,
`invalidations`, `confirmations`, and `contradictions` must now be present as
list-shaped `scenario_json` fields before `macro_module_view_v3` can render
overview evidence, structured analysis, decision-console rows, future
catalysts, or Watchlist rules.

Empty lists remain valid explicit projection output. Missing list fields are
malformed read-model payloads and are no longer converted into empty public
sections by `_mapping_list(scenario.get(...))`.

## 2026-06-22 Continuation Note — Base Scenario Field Hard Cut

This continuation removes cross-field repairs from the overview
`structured_analysis.market_thesis` row. The base scenario case must now carry
its own `thesis`, `trade`, and `invalidation` fields before the module view can
render the market-thesis row.

The module view no longer substitutes the regime label for a missing thesis,
does not borrow `trade_map` labels for a missing base-case trade, and does not
borrow scenario invalidation rows for a missing base-case invalidation. Those
fields are projection output, not display fallbacks assembled at request time.

## 2026-06-22 Continuation Note — Watchlist Asset Field Hard Cut

This continuation removes trade-leg display repairs from overview Watchlist
assets. Each `trade_map[].legs[]` asset row must now carry explicit `symbol`,
`label`, and `action` fields before the module view can render it into
`decision_console.watchlist_alerts.assets`.

The module view no longer substitutes `symbol` for a missing label, no longer
uses `label` as the asset key when `symbol` is absent, and no longer emits an
asset row with a blank action. Watchlist asset rows are projection output from
the macro scenario/trade-map contract, not request-time UI repairs.

## 2026-06-22 Continuation Note — Scenario Rule Identity Hard Cut

This continuation removes label-based identity repairs from overview scenario
rules. Scenario watch triggers must now carry an explicit stable `code` before
they can render into `decision_console.future_catalysts.rows` or
`decision_console.watchlist_alerts.rules`.

The module view no longer builds `watch:*` or Watchlist rule keys from display
labels when `code` is absent. Labels remain display text only; rule identity is
projection output from `scenario_json`, not a request-time compatibility key.

## 2026-06-22 Continuation Note — Event Catalyst Identity Hard Cut

This continuation removes label-based identity repairs from official macro event
catalysts. Event catalysts must now carry an explicit stable `code` before they
can render into `decision_console.future_catalysts.rows` or
`module_read.market_event_flow.rows`.

The module view no longer builds event keys from display labels when the
persisted event candidate is malformed. Official calendar, Treasury auction,
and Fed text rows already derive `code` from the persisted event series key;
request-time rendering now fails malformed displayable rows instead of using a
label as a compatibility identity.

## 2026-06-22 Continuation Note — Event Catalyst Source Hard Cut

This continuation removes empty-source repairs from official macro event
catalysts. Event catalysts must now carry an explicit source label before they
can render into `decision_console.future_catalysts.rows` or
`module_read.market_event_flow.rows`.

The module view no longer emits event rows with `source=""` when the persisted
event candidate is malformed. Official calendar, Treasury auction, and Fed text
events remain source-backed through their persisted provider/source metadata;
missing source is surfaced as a broken projection contract instead of a blank
public event row.

## 2026-06-22 Continuation Note — Event Catalyst Kind Hard Cut

This continuation removes empty-kind repairs from overview market-event-flow
rows. Official macro event candidates must now carry an explicit `kind` before
they can render into `module_read.market_event_flow.rows`.

The module view no longer lets a missing event kind be classified from code and
then published as `kind=""`. Event type is display-contract metadata from the
projection candidate, not a request-time compatibility field.

## 2026-06-22 Continuation Note — News Event Identity Hard Cut

This continuation removes headline and `news_item_id` identity repairs from
overview market-event-flow news rows. Source-backed news events must now carry
an explicit `row_id` before they can render into
`module_read.market_event_flow.rows`.

The module view no longer builds news event keys from `news_item_id` or the
headline when the macro caller passes a malformed news row. News event identity
belongs to the upstream read-model row, not a request-time compatibility key.

## 2026-06-22 Continuation Note — News Event Scope Hard Cut

This continuation removes generic market-scope repairs from overview
market-event-flow news rows. Source-backed news events must now carry an
explicit, recognized `market_scope.primary` before they can render into
`module_read.market_event_flow.rows`.

The module view no longer defaults missing scope to `market_event` or unknown
scope labels to `市场事件`. News event scope is upstream read-model metadata, not
request-time compatibility category text.

## 2026-06-22 Continuation Note — News Event Impact Class Hard Cut

This continuation removes conservative impact repairs from overview
market-event-flow news rows. Source-backed news events must now carry an
explicit, recognized `signal.agent_signal.decision_class` before they can render
`impact`, `impact_label`, `severity`, and `severity_label` into
`module_read.market_event_flow.rows`.

The module view no longer borrows `alert_eligibility.decision_class` to repair a
missing agent signal and no longer defaults missing or unknown decision classes
to `mainline_context` / `不改主线` / low severity. News event impact class is
upstream signal metadata, not request-time risk-softening copy.

## 2026-06-22 Continuation Note — News Event Date Hard Cut

This continuation removes raw timestamp repairs from overview market-event-flow
news rows. Source-backed news events must now carry the upstream page-row
`latest_at_ms` value before they can render the public `date` field into
`module_read.market_event_flow.rows`.

The module view no longer repairs missing `latest_at_ms` from `published_at` or
`observed_at`. News event timing comes from the News page read model's canonical
projected timestamp, not request-time raw item timestamp aliases.

## 2026-06-22 Continuation Note — News Event Display Field Hard Cut

This continuation removes silent display-field drops from overview
market-event-flow news rows. Source-backed news events must now carry explicit
`headline`, `summary`, and `source_domain` values before they can render into
`module_read.market_event_flow.rows`.

The module view no longer returns `None` when a malformed News page row lacks
display text or source-domain metadata. News event display fields are upstream
read-model output, not optional request-time presentation hints that can be
hidden from the macro page.

## 2026-06-22 Continuation Note — Official Event Display Field Hard Cut

This continuation removes silent display-field drops from official macro event
rows. Official calendar and auction event candidates must now carry explicit
`label` and `detail` values before they can render into
`decision_console.future_catalysts.rows`; market-event-flow rows must also
carry explicit `observed_at` before they can render their public `date`.

The module view no longer treats missing official event display metadata as
"no event". Missing labels, details, or event dates are malformed projection
rows, not request-time reasons to hide source-backed macro catalysts from the
page.

## 2026-06-22 Continuation Note — Scenario Rule Display Field Hard Cut

This continuation removes silent display-field drops from scenario watch
trigger and Watchlist rule rows. Scenario watch triggers must now carry
explicit `label`, `detail`, and a recognized `time_window` before they can
render into `decision_console.future_catalysts.rows`; Watchlist watch and
invalidation rules must carry explicit `label` and `detail`.

The module view no longer treats malformed scenario rules as "no rule".
Scenario rule display fields are part of the persisted `scenario_json`
contract emitted by the macro scenario engine, not request-time optional copy
that can be hidden from the macro page.

## 2026-06-22 Continuation Note — Quality Blocker Evidence Hard Cut

This continuation removes silent quality-blocker drops from the overview
decision console and Watchlist. Scenario `quality_blockers` must now carry
explicit `evidence_label` or `remediation_hint` before they can render into
`decision_console.quality_blockers` or Watchlist quality rules.

The module view no longer treats a malformed quality blocker as "no blocker".
Quality blockers are the page's trust boundary: missing repair/evidence copy is
a broken projection contract, not a request-time reason to hide degraded macro
state.

## 2026-06-22 Continuation Note — Module Evidence Item Hard Cut

This continuation removes silent evidence-row drops from overview
`module_evidence`. Scenario confirmations, contradictions, watch triggers, and
invalidations must now carry explicit `code`, `label`, and `evidence_label`
before they can render into the public module evidence payload.

The module view no longer filters malformed evidence rows with
`if item is not None`. Missing scenario evidence identity or display copy is a
broken `scenario_json` projection contract, not a request-time reason to make
the macro page look less uncertain.

## 2026-06-22 Continuation Note — Top Changes Signal Hard Cut

This continuation removes silent top-change drops from the overview decision
console. Scenario `top_changes` rows must now carry explicit `code`, `label`,
`kind`, and `evidence_label` before they can render into
`decision_console.top_changes`.

The module view no longer filters malformed top-change rows with
`if item is not None`. The first-screen change tape is projection output; a
missing top-change identity or display field is a broken `scenario_json`
contract, not a request-time reason to hide the driver from the operator.

## 2026-06-22 Continuation Note — Structured Signal Line Hard Cut

This continuation removes silent structured-analysis evidence drops from the
overview market thesis. Scenario `top_changes` and `confirmations` rows must
now carry explicit `label` and `evidence_label` before they can contribute to
`module_read.structured_analysis.rows[*].evidence`.

The module view no longer filters malformed structured signal lines with
`if line`. The cross-domain judgement chain is projection output; missing
evidence copy is a broken `scenario_json` contract, not a request-time reason
to make the thesis look clean but under-supported.

## 2026-06-22 Continuation Note — Judgement Review Window Hard Cut

This continuation removes silent judgement-review window drops from the
overview decision console. `holding_period_review.rows` must now carry explicit
`horizon`, `label`, `status`, `status_label`, `sample_count`, `hit_count`,
`win_rate_label`, `pnl_usd`, and `average_signed_return_pct` before they can
render into `decision_console.judgement_review`.

The module view no longer filters malformed holding windows with
`if row is not None`. The holding-period generator also stops emitting
zero-sample `0/0` windows; unsampled horizons are omitted at source, while
empty direct row construction is rejected. A judgement review with missing
metrics is a broken projection contract, not a request-time reason to hide the
bad window or manufacture a neutral-looking replay.

## 2026-06-22 Continuation Note — Trade Map Item Hard Cut

This continuation removes silent trade-map item drops from the overview
decision console. Scenario `trade_map` rows must now carry explicit
`expression` and `label` before they can render into
`decision_console.trade_map`, Watchlist assets, or judgement review.

The module view no longer filters malformed trade-map rows with
`if item is not None`. Trade-map identity and display label are part of the
persisted `scenario_json` contract; a missing expression or label is a broken
projection row, not a request-time reason to hide the trade idea from the
operator.

## 2026-06-22 Continuation Note — Compact Quality Blocker Filter Hard Cut

This continuation removes the remaining compact quality-blocker compatibility
filter from the overview decision console. Scenario `quality_blockers` rows
already fail fast when required label, severity, or evidence/remediation fields
are missing; the decision console now maps them directly into
`decision_console.quality_blockers`.

The module view no longer keeps an `if item is not None` escape hatch around
`_compact_quality_blocker(...)`. Quality blockers are trust-boundary rows; a
malformed blocker should break the projection contract visibly rather than be
silently omitted from the operator's risk picture.

## 2026-06-22 Continuation Note — Watchlist Rule Filter Hard Cut

This continuation removes the remaining Watchlist rule compatibility filters
from the overview decision console. Scenario `watch_triggers`,
`invalidations`, and quality-blocker rows already fail fast when required
`code`, `label`, or detail/evidence fields are missing; `_watchlist_rules(...)`
now maps those rows directly into `decision_console.watchlist_alerts.rules`.

The module view no longer keeps `if row is not None` escape hatches around
`_watchlist_rule(...)`. Watchlist rules are operator alert rows; malformed
rules should break the projection contract visibly rather than disappear from
the macro page's trigger/invalidation picture.

## 2026-06-22 Continuation Note — Future Watch Catalyst Filter Hard Cut

This continuation removes the remaining future-watch catalyst compatibility
filter from the overview decision console. Scenario `watch_triggers` already
fail fast when required `code`, `label`, `detail`, `time_window`, or `severity`
fields are missing; `_future_catalysts(...)` now maps those scenario trigger
rows directly into `decision_console.future_catalysts.rows`.

The module view no longer keeps an `if row is not None` escape hatch around
`_future_watch_catalyst(...)`. Official event candidates still keep their
explicit kind/date filter because it is the business selection for future
24h/72h events, not a malformed-row compatibility path.

## 2026-06-22 Continuation Note — Judgement Review Item Filter Hard Cut

This continuation removes the judgement-review item compatibility filter from
the overview decision console. The review section still selects only trade-map
items with explicit `holding_period_review.rows`, but selected items now must
carry explicit `expression`, `label`, and complete holding-window fields before
they can render into `decision_console.judgement_review`.

The module view no longer keeps `return None` in `_judgement_review_row(...)`
or an `if row is not None` escape hatch in `_judgement_review(...)`. Missing
review rows remain an honest absent review section; malformed selected review
items are projection-contract failures, not request-time rows to hide.

## 2026-06-22 Continuation Note — Structured Regime Label Hard Cut

This continuation removes the remaining structured-analysis regime-label
compatibility fallback from the overview module read. Domain diagnostics must
now carry an explicit `regime_label` or, for the yield-curve diagnostic, an
explicit `shape_label` before they can render into
`module_read.structured_analysis.rows[*].regime_label`.

The module view no longer lets a diagnostic section title or generic
"insufficient history" copy masquerade as the public regime label. A
structured-analysis row without an explicit regime/shape display label is a
broken diagnostic projection contract, not a request-time cue to show vague
state to the operator.

## 2026-06-22 Continuation Note — Structured Fed Communication Label Hard Cut

This continuation removes the remaining generic Fed-document label fallback
from the overview structured-analysis Fed communication row. Fed text catalyst
evidence must now carry an explicit `label` before it can render into
`module_read.structured_analysis.rows[*].evidence`.

The module view no longer lets `"Fed 文档"` masquerade as source-backed
display copy when the event projection omitted a label. A Fed communication
row without a concrete event label is a broken catalyst projection contract,
not a request-time reason to show generic macro commentary.

## 2026-06-22 Continuation Note — Structured Market Thesis Evidence Hard Cut

This continuation removes the remaining market-thesis compatibility drop from
the overview structured-analysis row. A scenario base case can no longer render
`module_read.structured_analysis.rows[*].key == "market_thesis"` unless it has
explicit source-backed evidence from `top_changes`, `confirmations`, or Trade
Map context.

The module view no longer treats an empty evidence list as a reason to hide the
entire market-thesis row. A base scenario with thesis, trade, and invalidation
but no evidence is a broken scenario projection contract, not an absent insight
for the operator page.

## 2026-06-22 Continuation Note — Structured Market Invalidation Helper Delete

This continuation deletes the dead `_structured_market_invalidation(...)`
helper from the overview module read. Base-case `invalidation` is already a
required field on the selected scenario case, and market-thesis rendering no
longer repairs it from scenario-level `invalidations`.

The module view no longer carries a helper whose only remaining behavior was
to assemble legacy invalidation text or return an empty string. Keeping that
function would imply an old cross-field fallback contract that no production
path should use.

## 2026-06-22 Continuation Note — Structured Market Trade Filter Hard Cut

This continuation removes the structured market-thesis Trade Map filter from
the overview module read. `trade_map` rows are part of the scenario projection
contract; once present, each row must carry explicit `expression` and `label`
before it can contribute Trade Map context to
`module_read.structured_analysis.rows[*].evidence`.

The module view no longer silently skips Trade Map rows with missing
`expression` or missing display `label` while rendering the market thesis.
Malformed Trade Map context now fails with the same `macro_trade_map_*`
contract errors used by the decision console instead of disappearing from the
structured read.

## 2026-06-22 Continuation Note — Structured Fed Communication Detail Hard Cut

This continuation removes the remaining structured Fed communication silent
drop from the overview module read. Once an official Fed text catalyst is
selected for `module_read.structured_analysis`, the catalyst must carry an
explicit `detail` before it can render the Fed communication row.

The module view no longer hides a malformed Fed text catalyst by returning
`None`, and it no longer keeps a dead `if not evidence: return None` branch
after evidence-label validation. Missing Fed communication detail is now a
projection-contract failure, not an absent structured-analysis row.

## 2026-06-22 Continuation Note — Structured Fed Communication Document Type Hard Cut

This continuation removes the generic Fed-document regime-label fallback from
the overview structured-analysis Fed communication row. Once an official Fed
text catalyst is selected, `document_type` must be present and one of the
known official document families before it can render
`module_read.structured_analysis.rows[*].regime_label`.

The module view no longer maps missing or unknown Fed text document types to
`"Fed 文档"`. Missing document type now fails as
`macro_structured_fed_communication_document_type_required`, and unknown
document type fails as
`macro_structured_fed_communication_document_type_unknown`, making malformed
Fed text projections visible instead of vague.

## 2026-06-22 Continuation Note — Structured Fed Communication Source Hard Cut

This continuation removes the remaining source omission from the overview
structured-analysis Fed communication row. Once an official Fed text catalyst
is selected, `source` must be present and non-empty before it can render into
`module_read.structured_analysis.rows[*].evidence`.

The module view no longer lets a Fed communication item display as a label and
speaker without naming the source of the official text. Missing source now
fails as `macro_structured_fed_communication_source_required`, making the
broken catalyst projection visible instead of turning source-backed macro
analysis into unsourced commentary.

## 2026-06-22 Continuation Note — Structured Fed Speech Speaker Hard Cut

This continuation removes the remaining title-derived speaker compatibility
path from Fed speech event catalysts and the overview structured-analysis Fed
communication row. Speech catalysts must now carry an explicit `speaker`
field before they can render speaker evidence.

The module view no longer infers a Fed official from the text before the first
comma in `document_title` or `value`, and it no longer lets a speech render
with label/source only. Missing speech speaker now fails as
`macro_structured_fed_communication_speaker_required`, making malformed Fed
speech projections visible instead of guessing from presentation text.

## 2026-06-22 Continuation Note — Event Catalyst Observed-At Hard Cut

This continuation removes the remaining event-date placeholder from macro
event catalyst display construction. Event observations must now carry an
explicit `observed_at` on the projected row or raw payload before the module
view can build official calendar, Treasury auction, Federal Reserve text, or
generic event catalyst detail.

The module view no longer renders event detail with `"--"` as a synthetic
date. Missing event observation dates now fail as
`macro_event_catalyst_observed_at_required`, making malformed event facts
visible before they can enter `module_read.market_event_flow` or the overview
structured-analysis Fed communication row.

## 2026-06-22 Continuation Note — Fed Text Event Title Hard Cut

This continuation removes the remaining description-as-title compatibility
path from Federal Reserve text event catalysts. Official Fed text events must
now carry explicit title text through the raw payload `value` or provenance
`document_title` before they can render a `fed_text` event detail.

The module view no longer lets `provenance.description` masquerade as the
trade-facing Fed document title, and it no longer renders a Fed text event
with only an observation date. Missing Fed text title now fails as
`macro_event_text_value_required`, making malformed official text projections
visible before they can enter `module_read.market_event_flow` or structured
Fed communication evidence.

## 2026-06-22 Continuation Note — Event Catalyst Source Name Hard Cut

This continuation removes the remaining raw-provider source compatibility
path from macro event catalyst construction. Event observations must now carry
an explicit materialized `source_name` before the module view can label the
official calendar, Treasury auction, Federal Reserve text, or generic event
catalyst source.

The module view no longer lets `raw_payload.provider` repair a missing
observation source. Missing event source metadata now fails as
`macro_event_catalyst_source_required`, keeping provider raw frame metadata
from masquerading as persisted fact provenance in
`module_read.market_event_flow` and structured Fed communication evidence.

## 2026-06-22 Continuation Note — Observation Tile Source Name Hard Cut

This continuation removes the remaining observation-source compatibility
fallback from module tile and table construction. Supplemental
`macro_observations` rows must now carry an explicit `source_name` before they
can override snapshot feature values and render public source labels.

The module view no longer repairs missing observation provenance from a legacy
`provider` field or by splitting the `series_key`. Missing observation source
metadata now fails as
`macro_module_view_observation_source_name_required:<concept_key>`, keeping
tile, table, and chart provenance tied to persisted fact metadata instead of
derived string shape.

## 2026-06-22 Continuation Note — Trade Map Action Checklist Row Hard Cut

This continuation removes the remaining silent-drop path from Trade Map action
checklist rendering. When a scenario `trade_map` item provides
`action_checklist` rows, each row must carry explicit `kind`, `kind_label`,
`label`, and `description` before the decision console can render the action.

The module view no longer skips malformed checklist rows while still showing a
paper-position review. Missing checklist display fields now fail as
`macro_trade_map_action_checklist_<field>_required`, making broken scenario
execution guidance visible instead of quietly shrinking the operator's action
surface.

## 2026-06-22 Continuation Note — Provenance Source Row Hard Cut

This continuation removes the remaining provenance source-row silent drop from
module view construction. Every observation passed into the module view must
carry explicit `source_name` before it can contribute to public provenance
rows, even when the observation is not part of the current module's tile set.

The module view no longer skips observations with missing source metadata while
still rendering the rest of the page. Missing provenance source metadata now
fails as `macro_module_view_observation_source_name_required:<concept_key>`,
keeping source coverage honest instead of quietly under-reporting malformed
facts.

## 2026-06-22 Continuation Note — Trade Map Action Checklist Shape Hard Cut

This continuation removes the remaining shape-level silent drop from Trade Map
action checklist rendering. When a scenario `trade_map` item provides
`action_checklist`, the value must now be an explicit sequence of mapping rows;
non-sequences, mappings masquerading as lists, scalar values, and non-mapping
rows fail before the decision console can render partial execution guidance.

The module view no longer routes `action_checklist` through `_mapping_list`,
which used to turn malformed checklist payloads into an empty checklist while
still appending the paper-position review. Invalid checklist containers now
fail as `macro_trade_map_action_checklist_rows_required`, and invalid row
shapes fail as `macro_trade_map_action_checklist_row_required`, preserving the
operator action surface as a formal scenario display contract instead of a
best-effort filter.

## 2026-06-22 Continuation Note — Availability Source Label Hard Cut

This continuation removes the remaining optional-source path from availability
note construction. When a snapshot feature is present, the module view now
requires explicit feature source metadata before it can render availability
notes for the module data-health table and overview source diagnostics.

The module view no longer lets `_source_label(...)` return `None` into
availability copy, which could produce source notes such as `None；...` while
the rest of the macro page appeared healthy. Missing availability feature
source metadata now fails as `macro_availability_source_required:<concept_key>`,
and the API contract fixture now carries the formal source shape expected from
current macro projections.

## 2026-06-22 Continuation Note — Feature Surface Source Label Hard Cut

This continuation removes the remaining optional-source path from the core
module feature surfaces. Macro tiles and table rows now require explicit
feature source metadata before they can expose `source_label`, `source_state`,
or source table cells.

The module view no longer lets `_tile(...)` or `_table_row(...)` render a
`None` source label while the feature value, quality, and history look valid.
Missing feature source metadata now fails as
`macro_module_view_feature_source_required:<concept_key>`, keeping module
headline tiles and sortable tables tied to formal snapshot provenance rather
than optional presentation text.

## 2026-06-22 Continuation Note — Feature Latest Value And Observed-At Hard Cut

This continuation removes the remaining latest-value placeholders from present
feature surfaces. When a snapshot feature is present, macro tiles and table
rows now require a formal `latest` mapping with explicit numeric `value` and
explicit `observed_at` before the feature can render as a current market fact.

The module view no longer lets `_tile(...)` or `_table_row(...)` turn malformed
feature latest metadata into `缺失` or `观测于 --`. Missing latest metadata now
fails as `macro_module_view_feature_latest_required:<concept_key>`, missing
values fail as `macro_module_view_feature_latest_value_required:<concept_key>`,
and missing observation dates fail as
`macro_module_view_feature_latest_observed_at_required:<concept_key>`, keeping
headline and table facts auditable instead of cosmetically filled.

## 2026-06-22 Continuation Note — Snapshot Header Time Metadata Hard Cut

This continuation removes the remaining time-placeholder path from real macro
module snapshot headers. When a `macro_view_snapshots` row exists, the module
view now requires explicit `asof_date` and `computed_at_ms` before rendering
the public snapshot header.

The module view no longer lets a real snapshot produce `截至 --` or
`计算于 --`; those labels remain only in the explicit missing-snapshot view.
Missing header time metadata now fails as
`macro_module_view_snapshot_asof_date_required` or
`macro_module_view_snapshot_computed_at_required`, keeping macro freshness and
projection currentness auditable instead of cosmetically filled.

## 2026-06-22 Continuation Note — Chart History Point Hard Cut

This continuation removes the remaining chart-history repair path from macro
module chart series. Chart points now come only from an explicit feature
`history` sequence; the module view no longer treats the current `latest`
value as a one-point line series when history is absent.

The module view now validates every provided history row before exposing it to
the frontend chart contract. Non-mapping rows fail as
`macro_chart_series_history_row_required:<concept_key>`, rows without
`observed_at` fail as
`macro_chart_series_history_observed_at_required:<concept_key>`, and rows
without a numeric `value` fail as
`macro_chart_series_history_value_required:<concept_key>`. Missing history is
shown as zero chart points and `insufficient_history`, keeping trend displays
from cosmetically implying history that the read model does not actually
carry.

## 2026-06-22 Continuation Note — Feature History Points Hard Cut

This continuation removes the remaining optional history-coverage path from
present macro feature surfaces. When a snapshot feature is present, tiles,
table rows, and availability coverage rows now require the formal
`history_points` field before rendering the feature as a usable module fact.

The module view no longer lets `_tile(...)` expose `history_points=None`, lets
`_table_row(...)` render current feature values without auditable history
coverage, or lets the availability table turn missing history metadata into the
generic `历史缺失` label. Missing feature history counts now fail as
`macro_module_view_feature_history_points_required:<concept_key>`, keeping
module readiness tied to the persisted current-series projection rather than
presentation-time gaps.

## 2026-06-22 Continuation Note — Availability Latest Metadata Hard Cut

This continuation removes the remaining latest-metadata placeholder path from
the availability table for present macro features. When a feature is present,
the availability row now requires the same formal `latest` mapping, numeric
`value`, and explicit `observed_at` used by headline tiles and sortable
feature tables.

The module view no longer lets `_availability_table(...)` turn malformed
present-feature latest metadata into `观测于 --` or a usable coverage row.
Missing latest metadata now fails as
`macro_module_view_feature_latest_required:<concept_key>`, missing values fail
as `macro_module_view_feature_latest_value_required:<concept_key>`, and
missing observation dates fail as
`macro_module_view_feature_latest_observed_at_required:<concept_key>`. The
explicit `观测于 --` label remains only for genuinely missing features, keeping
availability diagnostics honest about absent observations versus malformed
present rows.

## 2026-06-22 Continuation Note — Feature Latest Unit Hard Cut

This continuation removes the remaining latest-unit compatibility path from
present macro feature surfaces. When a snapshot feature is present, macro
tiles, table rows, chart series, and availability rows now require the formal
`latest.unit` field before the feature can render as a current market fact.

The module view no longer lets `_tile(...)` pass through `None` for `unit`, nor
lets `_table_row(...)`, `_chart_series(...)`, or `_availability_table(...)`
mask missing fact units behind catalog `unit_label` presentation metadata.
Missing latest unit metadata now fails as
`macro_module_view_feature_latest_unit_required:<concept_key>`, keeping numeric
macro values tied to their persisted observation unit rather than a label-only
catalog fallback.

## 2026-06-22 Continuation Note — Feature Display Metadata Hard Cut

This continuation removes the remaining catalog-fill path from present macro
feature display metadata. When a snapshot feature is present, the module view
now requires the feature row itself to carry `label`, `short_label`,
`description`, and `unit_label` before tiles, table rows, or chart series can
render it.

The request-time module view no longer uses `MACRO_CONCEPT_METADATA` to repair
malformed `features_json` rows. Missing present-feature display metadata now
fails as `macro_module_view_feature_<field>_required:<concept_key>`, keeping
the public module payload tied to the current read model rather than
presentation-time catalog fallback. Observation supplements still construct a
complete feature at their boundary before joining the module feature map.

## 2026-06-22 Continuation Note — Feature Engine Metadata Hard Cut

This continuation removes raw key/unit fallback from the macro feature writer.
When `MacroViewProjectionWorker` rebuilds the current macro snapshot through
`build_macro_features(...)`, every feature now requires catalog metadata for
`label`, `short_label`, `description`, and `unit_label` before it can be written
into `features_json`.

The feature engine no longer writes `concept_key` as a display label, no longer
uses `label` as a substitute for `short_label`, no longer emits an empty
description, and no longer uses the raw observation unit as `unit_label`.
Missing writer-side display metadata now fails as
`macro_feature_metadata_<field>_required:<concept_key>`, keeping the current
read model complete at write time instead of relying on API shaping repairs.

## 2026-06-22 Continuation Note — Feature Engine Source And Observed-At Hard Cut

This continuation removes the remaining empty-source and missing-date fallback
paths from the macro feature writer. When `build_macro_features(...)` writes a
feature into `features_json`, the latest source observation must now carry
explicit `source_name`, explicit `series_key`, and at least one valid
`observed_at` date accepted by the macro observation identity rules.

The feature engine no longer writes `source.name=""`, `source.series_key=""`,
or a no-date feature assembled from an empty observation placeholder. Missing
writer-side source metadata now fails as
`macro_feature_source_name_required:<concept_key>` or
`macro_feature_series_key_required:<concept_key>`, and rows without any valid
macro observation date fail as `macro_feature_observed_at_required:<concept_key>`.
This keeps `macro_view_snapshots.features_json` source-auditable at write time
instead of passing malformed current facts down to API shaping.

## 2026-06-22 Continuation Note — Feature Engine Latest Unit Hard Cut

This continuation moves the latest-unit contract into the macro feature writer.
When `build_macro_features(...)` writes a numeric or non-numeric feature into
`features_json`, the latest source observation must now carry an explicit
`unit` before the feature can be persisted as a current macro fact.

The feature engine no longer writes `latest.unit=None` or relays a raw optional
unit value without validation. Missing writer-side latest unit metadata now
fails as `macro_feature_unit_required:<concept_key>`, keeping
`macro_view_snapshots.features_json` aligned with the module-view contract that
requires present feature values to include a real observation unit.

## 2026-06-22 Continuation Note — Feature Engine Frequency Hard Cut

This continuation removes the remaining daily-frequency fallback from the
macro feature writer. When `build_macro_features(...)` computes
`freshness_days` and `stale_after_days`, the latest source observation must now
carry an explicit supported `frequency` before the feature can be written into
`features_json`.

The feature engine no longer turns missing, blank, or unknown frequency values
into a daily freshness window. Missing writer-side frequency metadata now fails
as `macro_feature_frequency_required:<concept_key>`, and unsupported values
fail as `macro_feature_frequency_unknown:<concept_key>:<frequency>`. This keeps
freshness and staleness diagnostics tied to persisted macro observation
cadence rather than a presentation-time daily default.

## 2026-06-23 Continuation Note — Feature Engine Data Quality Hard Cut

This continuation removes the remaining missing-quality-to-ok fallback from the
macro feature writer. When `build_macro_features(...)` writes a feature into
`macro_view_snapshots.features_json`, every source observation inspected for
series data quality must now carry explicit `data_quality` metadata before the
feature can be persisted as a current macro fact.

The feature engine no longer turns missing or blank `data_quality` values into
`ok`. Missing writer-side data-quality metadata now fails as
`macro_feature_data_quality_required:<concept_key>`. This keeps data-health
warnings tied to persisted macro observation quality rather than a silent
healthy default.

## 2026-06-23 Continuation Note — Feature Engine Concept Key Hard Cut

This continuation removes the silent malformed-row drop from the macro feature
writer. When `build_macro_features(...)` groups observations for the current
macro snapshot, every input observation must now carry an explicit non-blank
`concept_key` before the writer can continue.

The feature engine no longer skips observations whose product key is missing
or blank. Missing writer-side concept identity now fails as
`macro_feature_concept_key_required`. This keeps malformed current facts from
disappearing before `MacroViewProjectionWorker` writes
`macro_view_snapshots.features_json`.

## 2026-06-23 Continuation Note — Feature Engine Observed-At Hard Cut

This continuation removes the remaining malformed-date drop from the macro
feature writer. When `build_macro_features(...)` deduplicates observations for
a concept, every input row must now carry an `observed_at` value accepted by
the macro observation identity rules before the writer can continue.

The feature engine no longer skips malformed dates when at least one valid row
exists for the same concept. Missing or invalid writer-side observation dates
now fail as `macro_feature_observed_at_required:<concept_key>`. This keeps
current macro snapshots from hiding malformed fact timestamps inside a
seemingly valid latest series.

## 2026-06-23 Continuation Note — Feature Engine Numeric Value Hard Cut

This continuation removes the raw `value` numeric fallback from the macro
feature writer. When `build_macro_features(...)` decides whether an observation
has numeric history, only the formal projected `value_numeric` field can
participate in calculations.

The feature engine no longer treats raw observation `value` as a substitute for
`value_numeric`. Rows without usable `value_numeric` remain non-numeric and
surface `missing_numeric_history` / `non_numeric_values:*` gaps instead of
manufacturing numeric latest, delta, z-score, percentile, or history points.

## 2026-06-23 Continuation Note — Asset Correlation Numeric Value Hard Cut

This continuation removes the raw `value` numeric fallback from the retained
asset-correlation support data. When `build_macro_asset_correlation(...)`
builds price series, only `macro_observation_series_rows.value_numeric` can
participate in asset returns and correlation pairs.

The asset-correlation builder no longer treats raw observation `value` as a
substitute for `value_numeric`. Rows without usable `value_numeric` are omitted
from price history, causing insufficient-history or insufficient-overlap gaps
instead of manufacturing an available pair from raw payload values.

## 2026-06-23 Continuation Note — Asset Correlation Observed-At Hard Cut

This continuation removes the malformed-date drop from the retained
asset-correlation support data. When `build_macro_asset_correlation(...)`
admits an observation for a selected asset, `observed_at` must now normalize
through the macro observation identity rules before the row can be considered.

The asset-correlation builder no longer drops timestamp-shaped or malformed
dates behind an older valid price row. Invalid writer-side asset observation
dates now fail as `macro_asset_correlation_observed_at_required:<concept_key>`,
keeping malformed current-series rows visible instead of quietly shrinking the
correlation sample.

## 2026-06-23 Continuation Note — Asset Correlation Source Metadata Hard Cut

This continuation removes the empty-source fallback from the retained
asset-correlation support data. When `build_macro_asset_correlation(...)`
admits an asset price observation into correlation history, the row must now
carry explicit `source_name` metadata before it can contribute to asset
payloads or pair calculations.

The asset-correlation builder no longer writes `source_name=""` or drops empty
sources from an otherwise available correlation payload. Missing writer-side
source metadata now fails as
`macro_asset_correlation_source_name_required:<concept_key>`, keeping retained
asset correlation evidence source-auditable.

## 2026-06-23 Continuation Note — Asset Correlation Ranking Metadata Hard Cut

This continuation removes the zero-ranking fallback from the retained
asset-correlation support data. When `build_macro_asset_correlation(...)`
dedupes same-day asset price rows or emits source audit metadata, the row must
now carry explicit integer `source_priority` and `ingested_at_ms`.

The asset-correlation builder no longer turns missing, blank, or non-integer
ranking metadata into `0`. Missing writer-side ranking metadata now fails as
`macro_asset_correlation_source_priority_required:<concept_key>` or
`macro_asset_correlation_ingested_at_ms_required:<concept_key>`, keeping
same-day source selection auditable instead of depending on sentinel ranks.

## 2026-06-23 Continuation Note — Asset Correlation Title Metadata Hard Cut

This continuation removes the raw concept-key title fallback from the retained
asset-correlation support data. When `build_macro_asset_correlation(...)`
emits an asset payload, the concept must now have explicit title metadata in
`ASSET_CORRELATION_TITLES`.

The asset-correlation builder no longer displays unknown assets as their raw
`concept_key`. Missing asset title metadata now fails as
`macro_asset_correlation_title_required:<concept_key>`, keeping retained
correlation payloads tied to the supported asset catalog rather than a
presentation-time identity fallback.

## 2026-06-23 Continuation Note — Gap Payload Concept Metadata Hard Cut

This continuation removes the concept-code label fallback from macro data
gap payloads. When `build_macro_data_gaps(...)` receives a `missing:<concept>`
gap from the current macro projection, that concept must now be registered in
`MACRO_CONCEPT_METADATA` before the gap can be rendered for module data-health
surfaces.

The gap payload builder no longer turns an unmapped `missing:<concept>` code
into a generic `数据质量缺口：missing_*` label. Missing concept metadata now
fails as `macro_gap_concept_metadata_required:<concept_key>`, and missing
display labels fail as `macro_gap_concept_label_required:<concept_key>`.
This keeps the macro page from hiding an unmodelled indicator behind a
generic data-quality message.

## 2026-06-23 Continuation Note — Gap Payload Missing Subject Hard Cut

This continuation removes automatic humanization for generic `*_missing`
gap codes. When `build_macro_data_gaps(...)` receives a missing-subject code
that is not a concept-specific `missing:<concept>` gap and not a special
computed gap, the subject must now be explicitly named in the macro gap
catalog.

The gap payload builder no longer converts unknown codes such as
`narrative_magic_missing` into plausible product text. Unknown missing
subjects now fail as `macro_gap_subject_required:<public_code>`, while the
known `macro_view_snapshot_missing` gap is explicitly named as
`宏观快照缺失`. This removes another presentation-time string repair path
from the macro data-health surface.

## 2026-06-23 Continuation Note — Scenario Feature Source Label Hard Cut

This continuation removes the empty source-label fallback from scenario
feature-change generation. When `build_macro_scenario(...)` promotes a
feature delta into `top_changes`, the feature must now carry a formal
`source.name` that resolves through the scenario source-label catalog.

The scenario engine no longer emits top-change descriptions or evidence labels
with an omitted source. Missing feature source metadata now fails as
`macro_scenario_feature_source_required:<concept_key>`, and unknown source
labels fail as `macro_scenario_source_label_required:<concept_key>:<source>`.
This keeps the trading-facing scenario rail source-auditable instead of
silently dropping provenance from important changes.

## 2026-06-23 Continuation Note — Scenario Feature Latest Metadata Hard Cut

This continuation removes partial latest-metadata rendering from scenario
feature-change generation. When `build_macro_scenario(...)` promotes a
feature delta into `top_changes`, the feature's `latest` payload must now
carry explicit `value`, `unit`, and `observed_at` metadata before the change
can be emitted.

The scenario engine no longer emits a top-change card with only a delta and
source while omitting latest value or as-of date. Missing latest value now
fails as `macro_scenario_feature_latest_value_required:<concept_key>`,
missing units fail as
`macro_scenario_feature_latest_unit_required:<concept_key>`, and missing
observation dates fail as
`macro_scenario_feature_latest_observed_at_required:<concept_key>`. This keeps
the trading-facing change rail from presenting incomplete context as an
actionable macro driver.

## 2026-06-23 Continuation Note — Module Scenario Severity Label Hard Cut

This continuation removes module-side severity-label derivation from compact
scenario signals. When overview module payloads render `top_changes`,
`confirmations`, or other compact scenario signals, any signal that carries a
`severity` must now also carry an explicit `severity_label` from the scenario
producer.

`_compact_signal(...)` no longer calls module-level severity label metadata as
a repair path for incomplete scenario items. Missing compact signal severity
labels now fail as `macro_compact_signal_severity_label_required`, keeping the
module read path from manufacturing scenario display copy after projection.

## 2026-06-23 Continuation Note — Module Quality Blocker Evidence Hard Cut

This continuation removes the `remediation_hint` display fallback from compact
scenario quality blockers. When overview module payloads render
`quality_blockers`, each blocker must now carry an explicit `evidence_label`
from the scenario producer before it can be shown in the decision console.

`_compact_quality_blocker(...)` no longer treats remediation instructions as
display evidence. Missing quality-blocker evidence now fails as
`macro_quality_blocker_evidence_required`, keeping the overview read path from
rewriting data-health remediation text into scenario evidence.

## 2026-06-23 Continuation Note — Module Watchlist Quality Detail Hard Cut

This continuation removes the `remediation_hint` fallback from watchlist
quality rules. When overview module payloads render quality blockers as
watchlist rows, each quality rule must now carry an explicit `detail` or
scenario `evidence_label`.

`_watchlist_rule_detail(...)` no longer treats data-health remediation text as
a rule detail. Missing quality-rule detail now fails as
`macro_watchlist_rule_detail_required`, keeping the watchlist rail from
turning repair instructions into market monitoring conditions.

## 2026-06-23 Continuation Note — Module Watchlist Severity Label Hard Cut

This continuation removes module-side severity-label derivation from watchlist
rules. When overview module payloads render `watch_triggers`, `invalidations`,
or quality blockers as watchlist rows, any row that carries `severity` must now
also carry an explicit `severity_label` from the scenario producer.

`_watchlist_rule(...)` no longer calls a module-level severity-label helper to
repair incomplete scenario payloads. Missing watchlist severity labels now fail
as `macro_watchlist_rule_severity_label_required`. `build_macro_scenario(...)`
now emits explicit severity labels for watch triggers and quality blockers,
including `error` and `warning` gap severities, so the read path consumes
projected display metadata instead of manufacturing it at presentation time.

## 2026-06-23 Continuation Note — Module Watchlist Window Label Hard Cut

This continuation removes module-side window-label derivation from watchlist
rules. When overview module payloads render a watchlist row with
`time_window`, the projected scenario payload must now also carry explicit
`time_window_label` display metadata.

`_watchlist_rule(...)` no longer copies raw `time_window` into
`window_label`. Missing watchlist window labels now fail as
`macro_watchlist_rule_window_label_required`. `build_macro_scenario(...)` now
emits `time_window_label` for all producer-owned watch triggers, keeping the
overview watchlist rail from turning raw timing codes such as `24h` and `72h`
into user-facing display labels inside the read path.

## 2026-06-23 Continuation Note — Future Watch Catalyst Window Label Hard Cut

This continuation removes module-side window-label derivation from overview
future 24/72h watch catalysts. Scenario watch triggers used in
`decision_console.future_catalysts` must now carry explicit
`time_window_label` display metadata in addition to the raw `time_window`
machine window.

`_future_watch_catalyst(...)` no longer copies raw `time_window` into
`window_label`. Missing future watch-catalyst window labels now fail as
`macro_future_watch_catalyst_window_label_required`, and watch-trigger
catalysts render projected labels such as `24小时` and `72小时`. Official
calendar and auction event catalysts remain governed by their event-candidate
window rules; this slice changes only scenario watch-trigger catalysts.

## 2026-06-23 Continuation Note — Future Watch Catalyst Severity Label Hard Cut

This continuation removes module-side severity-label derivation from overview
future 24/72h watch catalysts. Scenario watch triggers used in
`decision_console.future_catalysts` must now carry explicit `severity_label`
display metadata in addition to the raw `severity` code.

`_future_watch_catalyst(...)` no longer calls module-side severity label
metadata to repair incomplete projected watch triggers. Missing future
watch-catalyst severity labels now fail as
`macro_future_watch_catalyst_severity_label_required`, keeping the
future-catalyst rail aligned with the producer-owned display contract already
used by compact scenario signals and watchlist rows.

## 2026-06-23 Continuation Note — Future Event Catalyst Display Label Hard Cut

This continuation removes future-event catalyst display fallback from the
decision-console 24/72h catalyst rail. Event candidates built from projected
`event:*` series rows now carry explicit `time_window`,
`time_window_label`, `severity`, and `severity_label` when they qualify for the
future catalyst strip.

`_future_event_catalyst(...)` no longer copies raw future windows into
`window_label` or derives severity labels while rendering the rail. Missing
future-event window labels now fail as
`macro_future_event_catalyst_window_label_required`, and missing future-event
severity labels fail as
`macro_future_event_catalyst_severity_label_required`. The event candidate
producer remains source-backed by persisted macro event observations; no
provider call, route fallback, or compatibility payload is added.

## 2026-06-23 Continuation Note — Module Evidence Severity Label Hard Cut

This continuation removes module-side severity-label derivation from
`module_evidence` evidence items. Overview evidence rows that carry a raw
`severity` code must now also carry explicit `severity_label` display metadata
from the projected scenario payload.

`_evidence_item(...)` no longer calls severity-label metadata to repair
incomplete evidence rows. Missing evidence-item severity labels now fail as
`macro_evidence_item_severity_label_required`, keeping the module-evidence rail
aligned with compact scenario signals, future catalysts, and watchlist rules.

## 2026-06-23 Continuation Note — Compact Quality Blocker Severity Label Hard Cut

This continuation removes module-side severity-label derivation from compact
decision-console quality blockers. Scenario `quality_blockers` rows that carry
`severity` must now also carry explicit `severity_label` display metadata from
the scenario producer before they can render in `decision_console`.

`_compact_quality_blocker(...)` no longer calls severity-label metadata to
repair incomplete quality blockers. Missing compact quality-blocker severity
labels now fail as `macro_quality_blocker_severity_label_required`, keeping the
quality-blocker rail aligned with module evidence, watchlist quality rules, and
future catalyst display contracts.

## 2026-06-23 Continuation Note — Module Evidence Time Window Label Hard Cut

This continuation removes optional window-label handling from `module_evidence`
evidence items. Evidence rows that carry `time_window` must now also carry
explicit `time_window_label` display metadata from the projected scenario
payload.

`_evidence_item(...)` no longer passes through a raw `time_window` without its
display label. Missing evidence-item window labels now fail as
`macro_evidence_item_time_window_label_required`, keeping raw horizon codes out
of module-evidence presentation paths.

## 2026-06-23 Continuation Note — Market Event Flow Display Label Hard Cut

This continuation removes module-side event-flow window and severity label
derivation from source-backed macro event rows. Event candidates built from
projected `event:*` series rows now carry explicit `event_flow_window`,
`event_flow_window_label`, `event_flow_severity`, and
`event_flow_severity_label` display metadata before they can render in
`module_read.market_event_flow`.

`_market_event_flow_row(...)` no longer calls event-window helpers to repair
incomplete event catalyst payloads. Missing market-event flow window labels now
fail as `macro_market_event_flow_window_label_required`, and missing severity
labels fail as `macro_market_event_flow_severity_label_required`. The public
row shape remains `window`, `window_label`, `severity`, and `severity_label`,
but those display values now come from the event-candidate producer instead of
the row renderer.

## 2026-06-23 Continuation Note — Market Event Flow Classification Hard Cut

This continuation removes module-side event-flow classification derivation from
source-backed macro event rows. Event candidates built from projected `event:*`
series rows now carry explicit `event_flow_category`,
`event_flow_category_label`, `event_flow_impact`,
`event_flow_impact_label`, and `event_flow_watch` metadata before they can
render in `module_read.market_event_flow`.

`_market_event_flow_row(...)` no longer classifies rows from `kind` or `code`
while rendering the public block. Missing event-flow category or impact display
fields now fail with explicit `macro_market_event_flow_*_required` errors,
keeping the event-flow row renderer from manufacturing trader-facing category,
impact, or watch text from low-level event identity.

## 2026-06-23 Continuation Note — Structured Fed Event Flow Evidence Hard Cut

This continuation removes event-flow classification derivation from the
overview structured Fed communication row. Fed text candidates built from
projected `event:*` series rows must now carry explicit
`event_flow_impact_label` and `event_flow_watch` metadata before structured
analysis can use them as evidence.

`_structured_fed_communication_evidence(...)` no longer calls event-flow
classification helpers to recover impact/watch copy from `kind` or `code`.
Missing impact labels now fail as
`macro_structured_fed_communication_impact_label_required`, and missing watch
text fails as `macro_structured_fed_communication_watch_required`. This keeps
the structured Fed read aligned with the same producer-owned event-flow
contract used by `module_read.market_event_flow`.

## 2026-06-23 Continuation Note — News Market Event Flow Contract Hard Cut

This continuation removes macro read-path derivation from News page rows before
they can render in overview `module_read.market_event_flow`. Source-backed News
rows must now carry an explicit `macro_event_flow` payload with `window`,
`window_label`, `severity`, `severity_label`, `category`,
`category_label`, `impact`, `impact_label`, and `watch` fields.

`_market_news_event_flow_row(...)` no longer derives macro event-flow category
from `market_scope`, severity/impact from `signal.agent_signal`, a recent
window label from generic event helpers, or watch text from `token_lanes`.
Missing `macro_event_flow` now fails as
`macro_market_news_event_flow_required`, and missing display fields fail
through field-specific `macro_market_news_event_*_required` errors. This keeps
News-backed macro rows from silently becoming trader-facing macro conclusions
unless the projected News row explicitly carries that macro event-flow contract.

## 2026-06-23 Continuation Note — News Macro Event Flow Projection

This continuation closes the producer-side gap exposed by the News market event
flow contract hard cut. News page rows now carry a formal nullable
`macro_event_flow` projection field, and the macro overview requests only rows
whose persisted `macro_event_flow_json` is present.

`build_news_page_row(...)` now emits `macro_event_flow` from ready News agent
briefs plus classified market scope at the `NewsPageProjectionWorker` write
boundary. `NewsRepository.list_news_page_rows(..., macro_event_flow=True)`
filters on `macro_event_flow_json IS NOT NULL` and requires the full event-flow
shape before returning rows to `NewsPageQuery`. The overview macro route uses
that filter instead of taking generic News rows and hoping the macro renderer
can interpret them.

The new `20260623_0182_news_page_macro_event_flow` migration adds
`news_page_rows.macro_event_flow_json`, backfills qualifying v5 rows from the
current projected agent brief / market scope / token-lane evidence, and adds a
partial latest-row index for macro event-flow reads. Non-qualifying News rows
remain explicit `macro_event_flow: None`; no compatibility default, historical
alias, provider call, hidden route fallback, or macro read-path derivation is
added.

## 2026-06-23 Continuation Note — Macro Query Token Auth Hard Cut

This continuation removes the macro HTTP query-token compatibility surface.
Macro routes now authenticate with the Bearer header only and reject `token`
query parameters instead of documenting or accepting them as an alternate
credential path.

`/api/macro`, `/api/macro/assets/correlation`, `/api/macro/series`, and
`/api/macro/modules/{module_id}` now call a macro-specific auth helper that
disables query-token lookup before authorizing. `routes_macro.py` no longer
declares `Query(alias="token")`, and macro correlation / series query
validators no longer include `token` in their allowlists. This keeps macro
HTTP auth aligned with the frontend API client's Bearer-header contract and
removes the old direct-link credential shim from the macro product surface
without changing non-macro routes that still have their own compatibility
burden.

The generated contract artefacts were regenerated after the route hard cut.
`docs/generated/openapi.json` and `web/src/lib/types/openapi.ts` no longer
publish `token` as a query parameter on `GET /api/macro/series`; generated
clients now see only the retained `concept_keys` and `window` query fields for
that endpoint.
