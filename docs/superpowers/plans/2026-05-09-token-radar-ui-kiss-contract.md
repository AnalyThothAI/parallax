# Token Radar UI KISS Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove frontend hard-coded token radar projection version gating so the UI renders valid current API rows after backend projection bumps.

**Architecture:** Keep backend projection versioning in storage and API metadata. Move the frontend contract to row-shape validation only by deleting the `TOKEN_RADAR_CONTRACT_VERSION` gate in `web/src/App.tsx`. Add a regression test that fails when a valid row is hidden only because `projection.version` changed.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, FastAPI/PostgreSQL backend unchanged.

---

## Pre-Flight

- [x] Spec is approved by user direction: "KISS remove v7/v6 version distinction complexity".
- [x] Worktree exists at `.worktrees/radar-scope-ui-debug`.
- [x] Branch is `codex/radar-scope-ui-debug`.

## File Structure

- `web/src/App.tsx`: remove frontend projection-version render gate.
- `web/src/App.test.tsx`: add regression coverage and test fixture override for arbitrary projection versions.
- `docs/superpowers/specs/2026-05-09-token-radar-ui-kiss-contract.md`: design boundary.
- `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract.md`: execution plan.
- `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract-verification.md`: final evidence.

## Task 1: Regression Test

**Files:**
- Modify: `web/src/App.test.tsx`

- [x] **Step 1: Add mock option for projection version**

Change the `mockApi` options type to include:

```ts
projectionVersion?: string;
```

Change token radar fixture creation to:

```ts
projection: assetFlowProjection(options.projectionVersion)
```

Change `assetFlowProjection` to:

```ts
function assetFlowProjection(version = "token-radar-fixture-current"): AssetFlowData["projection"] {
  return {
    status: "fresh",
    version,
    source: "token_radar_rows",
    source_max_received_at_ms: 1_777_746_300_000,
    computed_at_ms: 1_777_746_300_000
  };
}
```

- [x] **Step 2: Add failing test**

Add a test near the Token Radar rendering tests:

```ts
it("renders valid token radar rows regardless of backend projection version metadata", async () => {
  mockApi({ projectionVersion: "token-radar-next-internal-version" });

  renderWithQuery(<App />);

  expect(await screen.findByRole("button", { name: "select token $UPEG" })).toBeInTheDocument();
  expect(screen.getByText("TOKEN RADAR")).toBeInTheDocument();
});
```

- [x] **Step 3: Verify RED**

Run:

```bash
npm --prefix web test -- src/App.test.tsx -t "renders valid token radar rows regardless of backend projection version metadata"
```

Expected before production change: FAIL because the UI shows no row when projection version does not match the hard-coded frontend constant.

## Task 2: Frontend KISS Contract

**Files:**
- Modify: `web/src/App.tsx:63`
- Modify: `web/src/App.tsx:1104-1112`

- [x] **Step 1: Delete frontend backend-version constant**

Remove:

```ts
const TOKEN_RADAR_CONTRACT_VERSION = "token-radar-v6-auditable";
```

- [x] **Step 2: Replace version gate with data-presence gate**

Change:

```ts
if (!data || data.projection.version !== TOKEN_RADAR_CONTRACT_VERSION) {
  return [];
}
```

to:

```ts
if (!data) {
  return [];
}
```

Keep:

```ts
return assetFlowRows(data).map((row) => tokenRadarRowToTokenItem(row, window, scope));
```

- [x] **Step 3: Verify GREEN**

Run:

```bash
npm --prefix web test -- src/App.test.tsx -t "renders valid token radar rows regardless of backend projection version metadata"
```

Expected after production change: PASS.

## Task 3: Focused And Full Verification

**Files:**
- Create: `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract-verification.md`

- [x] **Step 1: Run focused web tests**

```bash
npm --prefix web test -- src/App.test.tsx
```

- [x] **Step 2: Run web build**

```bash
npm --prefix web run build
```

- [x] **Step 3: Run required project verification**

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall src tests
```

- [x] **Step 4: Rebuild Docker and smoke API/UI**

```bash
docker compose up -d --build app
TOKEN=$(curl -sS http://127.0.0.1:8765/api/bootstrap | jq -r '.data.ws_token')
curl -sS -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8765/api/token-radar?window=5m&scope=all&limit=5" | jq '{status:.data.projection.status, version:.data.projection.version, targets:(.data.targets|length), attention:(.data.attention|length)}'
curl -sS -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=5" | jq '{status:.data.projection.status, version:.data.projection.version, targets:(.data.targets|length), attention:(.data.attention|length)}'
```

Use Browser/Playwright to open `http://127.0.0.1:8765` and verify the Token Radar count is non-zero for `all` scope when API rows exist.

## Rollout

1. Merge frontend KISS change.
2. Rebuild Docker app so bundled web assets include the gate removal.
3. Verify `/api/token-radar` and UI render current rows.

## Rollback

Revert this frontend commit. Backend projection data remains untouched because this plan does not alter storage, migrations, extraction, resolution, or scoring.

## Acceptance Test Commands

- AC1: `npm --prefix web test -- src/App.test.tsx -t "renders valid token radar rows regardless of backend projection version metadata"`
- AC2: `rg -n "token-radar-v6|token-radar-v7|TOKEN_RADAR_CONTRACT_VERSION" web/src`
- AC3: `uv run pytest tests/test_asset_flow_service.py::test_asset_flow_reads_token_radar_projection_rows`
