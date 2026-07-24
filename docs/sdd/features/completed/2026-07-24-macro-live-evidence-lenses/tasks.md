# Tasks — Macro Live Evidence Lenses and DeepAgents Research Separation

**Status**: Verified
**Owning plan**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses/plan.md`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Branch**: `codex/deepagents-macro-hard-cut`
**Approved by**: user and GitHub Issue #8
**Approved at**: 2026-07-24

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | Issue #8 and `spec.md` settle live/frozen clocks, six categories, and removed semantics. |
| Checklist | `spec.md` maps every product requirement to an external quality gate. |
| Analyze | `plan.md` traces facts, research, API, frontend, storage, rollout, and recovery owners. |
| Implement | Tasks start with failing contracts and preserve the DeepAgents hard-cut implementation. |
| Verify | `verification.md` records exact successful command and production runtime receipts. |

## Tasks

### Task 1 — Establish active SDD and failing contracts

- **File(s)**: `docs/sdd/features/active/2026-07-24-macro-live-evidence-lenses`, `tests/unit/test_api_macro_contract.py`, `web/tests/routes/macro.route.test.tsx`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/sdd/features/active/2026-07-24-macro-live-evidence-lenses`, `tests/unit/test_api_macro_contract.py`, `web/tests/routes/macro.route.test.tsx`
- **Conflict set**: `src/parallax/domains/macro_intel`; `web/src/features/macro`
- **Failing test first**: `tests/unit/test_api_macro_contract.py::test_macro_live_dashboard_reads_persisted_facts_only`
- **Implementation**: Encode Issue #8 and add contract-level failures before production edits.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py`
- **Status**: [x]

### Task 2 — Implement catalog, direct fact reads, and descriptive assembly

- **File(s)**: `src/parallax/domains/macro_intel`, `tests/unit/domains/macro_intel`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `src/parallax/domains/macro_intel`, `tests/unit/domains/macro_intel`
- **Conflict set**: `src/parallax/app/surfaces/api`; `src/parallax/platform/db`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_live_evidence.py::test_live_view_keeps_missing_rows_local_and_uncatalogued_visible`
- **Implementation**: Add presentation metadata, indexed material-fact reads, row-local missing states, bounded history, and transparent calculations.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q`
- **Status**: [x]

### Task 3 — Implement the persisted-only live evidence API

- **File(s)**: `src/parallax/app/surfaces/api`, `tests/unit/test_api_macro_contract.py`, `docs/generated/openapi.json`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `src/parallax/app/surfaces/api`, `tests/unit/test_api_macro_contract.py`, `docs/generated/openapi.json`
- **Conflict set**: `web/src/lib/types/openapi.ts`; `src/parallax/app/runtime/repository_session.py`
- **Failing test first**: `tests/unit/test_api_macro_contract.py::test_macro_live_dashboard_reads_persisted_facts_only`
- **Implementation**: Add exact schemas and one authenticated parameterized GET route with bounded windows and zero execution side effects.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q`
- **Status**: [x]

### Task 4 — Implement dashboard, detail routes, and separated research route

- **File(s)**: `web/src/features/macro`, `web/src/routes/router.tsx`, `web/tests`, `src/parallax/app/surfaces/api/app.py`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `web/src/features/macro`, `web/src/routes/router.tsx`, `web/tests`, `src/parallax/app/surfaces/api/app.py`
- **Conflict set**: `web/src/features/cockpit`; `web/src/styles`
- **Failing test first**: `web/tests/routes/macro.route.test.tsx::renders_live_dashboard_and_research_card`
- **Implementation**: Add one feature-owned query family, URL window state, six summaries, complete searchable rows, charts, refresh health, responsive detail pages, and `/macro/research`.
- **Verification**: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx`
- **Status**: [x]

### Task 5 — Align generated contracts, docs, and architecture

- **File(s)**: `docs/`, `AGENTS.md`, `CLAUDE.md`, `web/src/lib/types/openapi.ts`, `tests/architecture`
- **Owner**: parent
- **Depends on**: Task 4
- **Touch set**: `docs/`, `AGENTS.md`, `CLAUDE.md`, `web/src/lib/types/openapi.ts`, `tests/architecture`
- **Conflict set**: `src/parallax/platform/db`; `web/src/features/macro`
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py::test_live_macro_surface_has_no_deterministic_judgment_contract`
- **Implementation**: Regenerate contracts/schema, update canonical product docs, and narrow residual gates to deterministic live-view structures without constraining Agent prose.
- **Verification**: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_docs_contract.py -q`
- **Status**: [x]

### Task 6 — Verify, merge, rebuild, migrate, and smoke-test

- **File(s)**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses`, `docs/generated/sdd-work-index.md`, `compose.yaml`
- **Owner**: parent
- **Depends on**: Task 5
- **Touch set**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses`, `docs/generated/sdd-work-index.md`, `compose.yaml`
- **Conflict set**: coordinate with main for final merge; coordinate with production-runtime for Docker deployment
- **Failing test first**: `tests/e2e/golden-paths/macro-live-evidence.spec.ts::macro_live_evidence_routes`
- **Implementation**: Run requirement-level gates, record receipts, move SDD to completed, commit the branch, merge to `main`, rebuild the exact image, migrate idempotently, and inspect authenticated APIs, routes, workers, readiness, and logs.
- **Verification**: `uv run python scripts/check_sdd_gate.py --feature 2026-07-24-macro-live-evidence-lenses --gate verify`
- **Status**: [x]
