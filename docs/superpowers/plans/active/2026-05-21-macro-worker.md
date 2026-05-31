# Macro Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable macro regime view chain: normalized macro observations -> projection worker -> API -> `/macro` frontend page.

**Architecture:** Add a `macro_intel` domain with PostgreSQL fact/read-model repositories, a deterministic regime engine, and one canonical worker. The UI consumes only `/api/macro` and does not recompute scores.

**Tech Stack:** Python 3.13, FastAPI, psycopg/JSONB, Alembic, WorkerBase, React + React Query + TypeScript.

---

**Status**: Approved
**Date**: 2026-05-21
**Owning spec**: `docs/superpowers/specs/active/2026-05-21-macro-worker.md`
**Worktree**: `.worktrees/macro-views-worker/`
**Branch**: `codex/macro-views-worker`

## Pre-flight

- [x] Spec is approved by the user's current request to continue with a macro page and worker based on the macro regime design.
- [x] Worktree exists at `.worktrees/macro-views-worker/` and `git branch --show-current` matches `codex/macro-views-worker`.
- [x] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes.

Known-failing baseline tests:

- `uv run python -m pytest tests/architecture/test_worker_inventory_contract.py tests/architecture/test_src_domain_architecture.py -q` exits 1 before this feature with five failures in `tests/architecture/test_src_domain_architecture.py`: missing `cex_market_intel` domain map entry, direct Pulse import of token constants, Narrative repository/query upward imports, Pulse raw SQL ownership, and OpenAI agent import of a Pulse service.

## File-level Edits

### Storage / migrations

- Create `src/parallax/platform/db/alembic/versions/20260521_0076_macro_views.py`.
  ```sql
  CREATE TABLE IF NOT EXISTS macro_observations (
    observation_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    series_key TEXT NOT NULL,
    observed_at DATE NOT NULL,
    value_numeric NUMERIC,
    unit TEXT,
    frequency TEXT,
    data_quality TEXT NOT NULL DEFAULT 'ok',
    source_ts TEXT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at_ms BIGINT NOT NULL
  );
  CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_observations_identity
    ON macro_observations(source_name, series_key, observed_at);
  CREATE INDEX IF NOT EXISTS idx_macro_observations_latest
    ON macro_observations(series_key, observed_at DESC, ingested_at_ms DESC);

  CREATE TABLE IF NOT EXISTS macro_view_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    projection_version TEXT NOT NULL,
    asof_date DATE NOT NULL,
    status TEXT NOT NULL,
    regime TEXT NOT NULL,
    overall_score NUMERIC,
    panels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at_ms BIGINT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_macro_view_snapshots_latest
    ON macro_view_snapshots(projection_version, computed_at_ms DESC);
  ```

### Backend domain

- Create `src/parallax/domains/macro_intel/__init__.py`.
- Create `src/parallax/domains/macro_intel/_constants.py`.
  - Define `MACRO_VIEW_PROJECTION_VERSION = "macro_regime_v1"`.
- Create `src/parallax/domains/macro_intel/ARCHITECTURE.md`.
  - Declare `macro_observations` as facts and `macro_view_snapshots` as a read model written only by `MacroViewProjectionWorker`.
- Create `src/parallax/domains/macro_intel/services/macro_regime_engine.py`.
  - Function: `build_macro_view_snapshot(observations: Sequence[Mapping[str, Any]], *, computed_at_ms: int) -> dict[str, Any]`.
  - Compute liquidity, rates, volatility, credit, and cross-asset panels from latest observations.
  - Emit explicit `data_gaps` when required series are missing.
  - Keep component scores transparent under `panels_json`.
- Create `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`.
  - Methods: `upsert_observation(observation: Mapping[str, Any])`, `latest_observations(series_keys: Sequence[str] | None = None)`, `insert_snapshot(snapshot: Mapping[str, Any])`, `latest_snapshot()`.
- Create `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`.
  - Subclass `WorkerBase`; `run_once_sync()` reads latest observations, builds a snapshot, inserts it, and returns `WorkerResult(processed=1, notes={"projection_version": "macro_regime_v1", "status": snapshot["status"]})`.

### Runtime wiring

- Modify `src/parallax/app/runtime/repository_session.py`.
  - Import `MacroIntelRepository`.
  - Add `macro_intel: MacroIntelRepository` to `RepositorySession`.
  - Instantiate `macro_intel=MacroIntelRepository(conn)`.
- Modify `src/parallax/platform/config/settings.py`.
  - Add `MacroViewProjectionWorkerSettings(PerWorkerSettings)` with `interval_seconds=300`, `batch_size=250`, `statement_timeout_seconds=30`, `advisory_lock_key=2026052109`.
  - Add `macro_view_projection` to `WorkersSettings`.
  - Add default workers YAML block for `macro_view_projection`.
- Modify `src/parallax/app/runtime/worker_registry.py`.
  - Add canonical worker key/class `macro_view_projection`.
  - Set start priority after CEX board and before Pulse.
- Create `src/parallax/app/runtime/worker_factories/macro_intel.py`.
  - Own `WORKER_KEYS = frozenset({"macro_view_projection"})`.
  - Construct `MacroViewProjectionWorker` when enabled.
- Modify `src/parallax/app/runtime/worker_factories/__init__.py`.
  - Register the macro factory in `worker_factory_specs()`.

### API

- Create `src/parallax/app/surfaces/api/routes_macro.py`.
  - `router = APIRouter()`.
  - `GET /macro` authenticates with `_authenticated_runtime`, reads `repos.macro_intel.latest_snapshot()`, and returns a stable data-gap payload when no snapshot exists.
- Modify `src/parallax/app/surfaces/api/http.py`.
  - Include `routes_macro.router`.

### Frontend

- Add macro contract types to `web/src/lib/types/frontend-contracts.ts` and export from `web/src/lib/types/index.ts`.
- Modify `web/src/shared/query/queryKeys.ts`.
  - Add `macro: () => ["macro"] as const`.
- Modify `web/src/shared/routing/paths.ts`.
  - Add `macroPath(): string`.
- Create `web/src/features/macro/api/useMacroQuery.ts`.
  - Fetch `/api/macro` with the token.
- Create `web/src/features/macro/MacroPage.tsx`.
  - Render one dense operator page: regime header, component score strip, transmission-chain panels, validation indicators, triggers, and data gaps.
- Create `web/src/features/macro/macro.css`.
  - Match the app's cockpit style with compact panels, no nested cards, stable panel heights, and responsive grid tracks.
- Create `web/src/features/macro/index.ts`.
- Create `web/src/routes/macro.route.tsx`.
- Modify `web/src/routes/AppRoutes.tsx`.
  - Import `MacroRoute` and add `<Route path="macro" element={<MacroRoute token={token ?? ""} />} />`.
- Modify `web/src/features/cockpit/ui/CockpitSideRail.tsx`.
  - Add `macroRouteMatch`, `macroPath()`, and a `Macro` rail button.

### Docs

- Modify `docs/ARCHITECTURE.md`.
  - Add `domains/macro_intel` to the system map and domain table.
  - Add `macro_observations` and `macro_view_snapshots` to facts/read-model ownership text.
- Modify `docs/WORKERS.md`.
  - Add `macro_view_projection` to the marker and inventory table.
  - Add wake/catch-up note: poll-only MVP.
- Modify `docs/FRONTEND.md`.
  - Document `/macro` as a deterministic macro state page.
- Modify `docs/CONTRACTS.md`.
  - Document `/api/macro` semantics.

### Tests

- Create `tests/unit/domains/macro_intel/test_macro_regime_engine.py`.
  - Test empty observations return `status="empty"` and panel/data-gap shape.
  - Test representative observations produce liquidity/rates/credit/vol panel scores and threshold triggers.
- Create `tests/unit/domains/macro_intel/test_macro_view_projection_worker.py`.
  - Use a fake repository session to verify worker reads observations, inserts one snapshot, and returns notes.
- Create `tests/unit/test_api_macro_contract.py`.
  - Use `TestClient` with fake runtime to verify `/api/macro` returns the latest snapshot and missing-snapshot data-gap envelope.
- Modify `tests/unit/test_bootstrap_worker_runtime_wiring.py`.
  - Assert `macro_view_projection` constructs with default settings.
- Create `web/tests/component/features/macro/MacroPage.test.tsx`.
  - Mock `getApi`, render loading/data-gap/populated states, and assert no local score recomputation.
- Create `web/tests/routes/macro.route.test.tsx`.
  - Render `/macro`, verify it calls `/api/macro`, and verify the side rail marks Macro active.

## PR Breakdown

1. **PR 1 — Macro read model spine**: migration, domain service/repository/worker, runtime wiring, backend tests, docs.
2. **PR 2 — Macro API and UI**: API route, frontend feature/route, UI tests, contract docs.

The user asked to land directly to `main`; this branch will be merged back to `main` after verification rather than opened as a separate PR unless redirected.

## Rollout Order

1. Apply migration with `uv run alembic upgrade head` in the deployment environment.
2. Run `macro_view_projection` once; with no data it should write an empty/degraded snapshot.
3. Import normalized macro observations through a future `macrodata-cli` importer or direct repository maintenance path.
4. Run worker again to compute the first populated snapshot.
5. Open `/macro` and verify API/UI render the latest snapshot.

## Rollback

- Code rollback: revert the feature commit or disable `workers.macro_view_projection.enabled`.
- Data rollback: `downgrade()` drops `macro_view_snapshots` and `macro_observations`. This removes imported macro facts, so export/retain source bundles before downgrade if production data exists.
- UI rollback: remove the `/macro` route and side rail button; API can remain harmless if worker disabled.

## Acceptance Test Commands

- AC1: `uv run python -m pytest tests/unit/domains/macro_intel/test_macro_regime_engine.py::test_empty_observations_emit_degraded_snapshot -q`
- AC2: `uv run python -m pytest tests/unit/domains/macro_intel/test_macro_regime_engine.py::test_representative_observations_emit_scores_and_triggers -q`
- AC3: `uv run python -m pytest tests/unit/test_api_macro_contract.py -q`
- AC4: `cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx`

## Verification

Record final output in `docs/superpowers/plans/active/2026-05-21-macro-worker-verification.md` before declaring completion. Run targeted backend/frontend tests, `uv run ruff check .`, `uv run mypy src`, and frontend type/lint checks. Run `make check-all`; if it still fails because of baseline architecture issues, include the exact pre-existing failures and confirm no new macro-related failures were introduced.
