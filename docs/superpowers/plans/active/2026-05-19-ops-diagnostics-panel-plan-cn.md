# Ops Diagnostics Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first read-only `/ops` diagnostics panel with backend aggregate diagnostics, allowlisted queue drilldown, and a frontend cockpit route.

**Architecture:** Add an application-runtime read model under `app/runtime/ops_diagnostics.py` that composes existing runtime status, provider health, worker status, queue summaries, and existing domain query results. Expose it through a thin authenticated `routes_ops.py` API surface and render it through a new feature-scoped frontend module under `web/src/features/ops`, keeping Radar, Signal Lab, and domain modules decoupled.

**Tech Stack:** Python 3.13, FastAPI, Pydantic API schemas, PostgreSQL read queries through existing pool/repository contexts, React 19, TanStack Query, Vite/Vitest, existing cockpit CSS tokens.

---

## File Structure

- Create `src/gmgn_twitter_intel/app/runtime/ops_diagnostics.py`: pure read-only diagnostics aggregator, status classification, redaction, queue allowlist query helpers.
- Create `src/gmgn_twitter_intel/app/surfaces/api/routes_ops.py`: authenticated ops endpoints; no business logic beyond input validation and response envelopes.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/http.py`: include the ops router.
- Modify `src/gmgn_twitter_intel/app/runtime/app.py`: add SPA fallback routes for `/ops`.
- Modify `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`: add loose named `OpsDiagnosticsData` and `OpsQueueData` envelope models.
- Create `tests/unit/test_ops_diagnostics.py`: unit tests for redaction, section failure isolation, queue classification, and invalid queue protection.
- Create `tests/unit/test_api_ops_contract.py`: FastAPI contract tests for auth, diagnostics response, and queue drilldown.
- Create `web/src/features/ops/api/useOpsDiagnosticsQuery.ts`: TanStack Query hooks for diagnostics and queue drilldown.
- Create `web/src/features/ops/model/opsDiagnostics.ts`: frontend types and small view-model helpers.
- Create `web/src/features/ops/ui/OpsDiagnosticsPage.tsx`: page composition.
- Create `web/src/features/ops/ui/ops.css`: feature-owned styles.
- Create `web/src/features/ops/index.ts`: feature exports.
- Create `web/src/routes/ops.route.tsx`: route wrapper that receives token.
- Modify `web/src/routes/AppRoutes.tsx`: mount `/ops` inside cockpit shell.
- Modify `web/src/shared/routing/paths.ts`: add `opsPath()`.
- Modify `web/src/features/cockpit/ui/CockpitSideRail.tsx`: add `Ops` navigation item without moving existing state.
- Modify `web/src/shared/query/queryKeys.ts`: add ops query keys.
- Create `web/tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx`: UI tests for status rendering and queue selection.
- Modify or add route/nav tests only if existing architecture tests require explicit allowlisting.

## Task 1: Backend Diagnostics Aggregator

**Files:**
- Create: `src/gmgn_twitter_intel/app/runtime/ops_diagnostics.py`
- Test: `tests/unit/test_ops_diagnostics.py`

- [x] **Step 1: Write failing tests**

```python
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.ops_diagnostics import (
    INVALID_QUEUE,
    ops_diagnostics_payload,
    ops_queue_payload,
    redact_diagnostics,
)


def test_redact_diagnostics_masks_secret_like_keys():
    payload = redact_diagnostics(
        {
            "api_key": "sk-live",
            "nested": {"ws_token": "secret-token", "safe": "ok"},
            "items": [{"dsn": "postgres://secret"}],
        }
    )

    assert payload["api_key"] == "<redacted>"
    assert payload["nested"]["ws_token"] == "<redacted>"
    assert payload["nested"]["safe"] == "ok"
    assert payload["items"][0]["dsn"] == "<redacted>"


def test_ops_diagnostics_survives_news_section_failure():
    runtime = FakeRuntime(news_error=RuntimeError("feed exploded"))

    payload = ops_diagnostics_payload(runtime, now_ms=10_000, since_hours=4, window="1h", scope="all")

    assert payload["schema_version"] == "ops.diagnostics.v1"
    assert payload["domains"]["news"]["status"] == "unknown"
    assert payload["domains"]["news"]["error_type"] == "RuntimeError"
    assert payload["workers"]
    assert payload["providers"]
    assert payload["queues"]


def test_ops_queue_payload_rejects_unknown_queue_without_sql():
    runtime = FakeRuntime()

    payload = ops_queue_payload(runtime, queue_name="events;drop table events", status=None, limit=20, now_ms=10_000)

    assert payload == INVALID_QUEUE
    assert runtime.db.api_pool.conn.executed == []


def test_ops_queue_payload_marks_dead_queue_blocked():
    runtime = FakeRuntime(queue_rows=[{"status": "dead", "count": 1}])

    payload = ops_queue_payload(runtime, queue_name="pulse_agent_jobs", status=None, limit=20, now_ms=10_000)

    assert payload["counts_by_status"]["dead"] == 1
    assert payload["summary"]["status"] == "blocked"
```

- [x] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_ops_diagnostics.py -q`

Expected: fail with `ModuleNotFoundError` for `gmgn_twitter_intel.app.runtime.ops_diagnostics`.

- [x] **Step 3: Implement aggregator**

Implement only read helpers:

- `ops_diagnostics_payload(runtime, now_ms, since_hours, window, scope) -> dict`
- `ops_queue_payload(runtime, queue_name, status, limit, now_ms) -> dict`
- `redact_diagnostics(value) -> value`
- `INVALID_QUEUE = {"error": "invalid_queue"}`

Use `canonical_workers_status_payload(runtime)`, `JOB_QUEUE_DESCRIPTORS`, provider health from `runtime.providers.asset_market.provider_health`, current provider `connection_state_payload()`, existing repository context for projection/news/notification summaries, and section wrappers that return `status="unknown"` on exceptions.

- [x] **Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/test_ops_diagnostics.py -q`

Expected: all tests pass.

## Task 2: Backend API Routes

**Files:**
- Create: `src/gmgn_twitter_intel/app/surfaces/api/routes_ops.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/http.py`
- Modify: `src/gmgn_twitter_intel/app/surfaces/api/schemas.py`
- Modify: `src/gmgn_twitter_intel/app/runtime/app.py`
- Test: `tests/unit/test_api_ops_contract.py`

- [x] **Step 1: Write failing API contract tests**

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router


def test_ops_diagnostics_requires_authentication():
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get("/api/ops/diagnostics")

    assert response.status_code == 401


def test_ops_diagnostics_returns_aggregate_payload():
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get(
            "/api/ops/diagnostics",
            params={"since_hours": 4, "window": "1h", "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["schema_version"] == "ops.diagnostics.v1"
    assert "workers" in body["data"]


def test_ops_queue_rejects_invalid_queue():
    app = _app(FakeRuntime())

    with TestClient(app) as client:
        response = client.get(
            "/api/ops/queues/not-real",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_queue"
```

- [x] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_api_ops_contract.py -q`

Expected: fail because `/api/ops/diagnostics` and `/api/ops/queues/{queue_name}` do not exist.

- [x] **Step 3: Implement thin API route**

`routes_ops.py` should:

- use `_authenticated_runtime`;
- validate `since_hours` with `Query(ge=1, le=168)`;
- validate `window` with `_window`;
- validate `scope` with `_scope`;
- call `ops_diagnostics_payload`;
- call `ops_queue_payload`;
- convert `INVALID_QUEUE` and invalid status to 400 envelopes;
- return `_json({"ok": True, "data": payload})`.

- [x] **Step 4: Wire router and SPA fallback**

Add `routes_ops` to `http.py`, add `OpsDiagnosticsData` and `OpsQueueData` schema classes to `schemas.py`, and add `/ops` plus `/ops/{path:path}` in `_mount_frontend`.

- [x] **Step 5: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py -q`

Expected: all tests pass.

## Task 3: Frontend Ops Feature

**Files:**
- Create: `web/src/features/ops/api/useOpsDiagnosticsQuery.ts`
- Create: `web/src/features/ops/model/opsDiagnostics.ts`
- Create: `web/src/features/ops/ui/OpsDiagnosticsPage.tsx`
- Create: `web/src/features/ops/ui/ops.css`
- Create: `web/src/features/ops/index.ts`
- Modify: `web/src/shared/query/queryKeys.ts`
- Test: `web/tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx`

- [x] **Step 1: Write failing UI tests**

```tsx
import { render, screen } from "@testing-library/react";
import { OpsDiagnosticsPage } from "@features/ops";

test("renders the main diagnostic regions", () => {
  render(<OpsDiagnosticsPage diagnostics={fakeDiagnostics} queue={null} loading={false} />);

  expect(screen.getByText("Ops Diagnostics")).toBeInTheDocument();
  expect(screen.getByText("Pipeline")).toBeInTheDocument();
  expect(screen.getByText("Providers")).toBeInTheDocument();
  expect(screen.getByText("Workers")).toBeInTheDocument();
  expect(screen.getByText("Queues")).toBeInTheDocument();
});
```

- [x] **Step 2: Run test to verify RED**

Run: `cd web && npm test -- tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx --runInBand`

Expected: fail because `@features/ops` does not exist.

- [x] **Step 3: Implement frontend feature**

Create typed view-model helpers and page components:

- `statusTone(status)` maps `ok | idle | disabled | degraded | blocked | unknown`.
- `useOpsDiagnosticsQuery({ token, window, scope, sinceHours })` calls `/api/ops/diagnostics`.
- `useOpsQueueQuery({ token, queueName, status, limit, enabled })` calls `/api/ops/queues/${queueName}`.
- `OpsDiagnosticsPage` renders loading/error/empty/data states and the six primary regions from the spec.

- [x] **Step 4: Run test to verify GREEN**

Run: `cd web && npm test -- tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx --runInBand`

Expected: all ops component tests pass.

## Task 4: Frontend Route And Navigation

**Files:**
- Create: `web/src/routes/ops.route.tsx`
- Modify: `web/src/routes/AppRoutes.tsx`
- Modify: `web/src/shared/routing/paths.ts`
- Modify: `web/src/features/cockpit/ui/CockpitSideRail.tsx`
- Test: existing side rail tests plus a small ops nav assertion.

- [x] **Step 1: Write failing nav test**

Add to `web/tests/component/features/cockpit/ui/CockpitSideRail.test.tsx`:

```tsx
expect(screen.getByRole("button", { name: /Ops/i })).toBeInTheDocument();
```

- [x] **Step 2: Run test to verify RED**

Run: `cd web && npm test -- tests/component/features/cockpit/ui/CockpitSideRail.test.tsx --runInBand`

Expected: fail because the side rail has no Ops nav item.

- [x] **Step 3: Implement route and nav**

- Add `opsPath()` to routing paths.
- Add `<Route path="ops" element={<OpsRoute token={token ?? ""} windowKey={windowKey} scope={scope} />} />` inside cockpit shell.
- Add a SideRail `Ops` button with active match `useMatch("/ops/*")`.

- [x] **Step 4: Run route/nav tests**

Run: `cd web && npm test -- tests/component/features/cockpit/ui/CockpitSideRail.test.tsx tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx --runInBand`

Expected: all selected tests pass.

## Task 5: Verification

**Files:**
- No new files unless verification exposes a defect.

- [x] **Step 1: Backend focused tests**

Run: `uv run pytest tests/unit/test_ops_diagnostics.py tests/unit/test_api_ops_contract.py -q`

Expected: pass.

- [x] **Step 2: Frontend focused tests**

Run: `cd web && npm test -- tests/component/features/ops/ui/OpsDiagnosticsPage.test.tsx tests/component/features/cockpit/ui/CockpitSideRail.test.tsx --runInBand`

Expected: pass.

- [x] **Step 3: Typecheck**

Run: `cd web && npm run typecheck`

Expected: pass.

- [x] **Step 4: Contract drift check**

Run: `uv run pytest tests/contract/test_openapi_drift.py -q`

Expected: either pass if generated OpenAPI remains compatible, or fail with an explicit generated OpenAPI update requirement.

## Self Review

- Spec coverage: covers read-only aggregate diagnostics, queue drilldown, redaction, partial failures, frontend `/ops` route, SPA fallback, and no new facts/workers.
- Coupling guard: ops code composes existing runtime and repository interfaces from the app layer only; domain modules do not import ops; frontend ops feature imports shared API/query/UI helpers but no Radar/Signal Lab internals.
- Placeholder scan: no `TBD`, no deferred implementation steps.
- Scope: mutation actions and task streams remain out of scope.
