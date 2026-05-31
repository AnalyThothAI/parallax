# Verification - Token Radar UI KISS Contract

**Date**: 2026-05-09
**Owning spec**: `docs/superpowers/specs/2026-05-09-token-radar-ui-kiss-contract.md`
**Owning plan**: `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract.md`
**Branch**: `codex/radar-scope-ui-debug`
**Diff**: `git diff main...codex/radar-scope-ui-debug` - frontend KISS gate removal, regression test, spec, plan, verification.

## Spec Compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - WHEN `/api/token-radar` response uses a new projection version and includes a valid row THEN the web UI SHALL render that token row. | Pass | Red/green test: `npm --prefix web test -- src/App.test.tsx -t "renders valid token radar rows regardless of backend projection version metadata"` failed before code change, then passed after deleting the gate. |
| AC2 - WHEN searching web source for `token-radar-v6` or `token-radar-v7` THEN no web production code SHALL contain those strings. | Pass | `rg -n "token-radar-v6|token-radar-v7|TOKEN_RADAR_CONTRACT_VERSION" web/src` returned no matches. |
| AC3 - WHEN backend tests inspect `projection.version` THEN they SHALL still see `TOKEN_RADAR_PROJECTION_VERSION` from the backend contract. | Pass | `uv run pytest` passed, including `tests/test_asset_flow_service.py`. No backend projection code changed. |

## Verification Commands

```text
$ npm --prefix web test -- src/App.test.tsx -t "renders valid token radar rows regardless of backend projection version metadata"
Before production change:
Test Files  1 failed (1)
Tests  1 failed | 50 skipped (51)
Failure: Unable to find role="button" and name "select token $UPEG"

After production change:
Test Files  1 passed (1)
Tests  1 passed | 50 skipped (51)
```

```text
$ npm --prefix web test -- src/App.test.tsx
Test Files  1 passed (1)
Tests  51 passed (51)
```

```text
$ npm --prefix web run build
vite v8.0.10 building client environment for production...
dist/index.html                   0.45 kB
dist/assets/index-BX6v4Nre.css   63.52 kB
dist/assets/index-BVep4PrD.js   373.68 kB
built in 288ms
```

```text
$ rg -n "token-radar-v6|token-radar-v7|TOKEN_RADAR_CONTRACT_VERSION" web/src
<no matches>
```

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest
338 passed, 133 skipped in 22.80s

$ uv run python -m compileall src tests
Completed successfully.
```

```text
$ docker compose -p parallax -f compose.yaml up -d --build app
parallax-migrate  Built
parallax-app      Built
Container parallax-app-1  Started
```

```text
$ curl -fsS http://127.0.0.1:8765/healthz
ok

$ curl -fsS http://127.0.0.1:8765/readyz | jq '{status:.status, reasons:.reasons, token_radar_projection:{worker_running:.token_radar_projection.worker_running,last_error:.token_radar_projection.last_error}}'
{
  "status": null,
  "reasons": [],
  "token_radar_projection": {
    "worker_running": true,
    "last_error": null
  }
}
```

```text
$ curl -sS -H "Authorization: Bearer <redacted>" "http://127.0.0.1:8765/api/token-radar?window=5m&scope=all&limit=5" | jq '{status:.data.projection.status, version:.data.projection.version, targets:(.data.targets|length), attention:(.data.attention|length)}'
{
  "status": "fresh",
  "version": "token-radar-v7-candidate-hydration",
  "targets": 5,
  "attention": 4
}

$ curl -sS -H "Authorization: Bearer <redacted>" "http://127.0.0.1:8765/api/token-radar?window=1h&scope=all&limit=5" | jq '{status:.data.projection.status, version:.data.projection.version, targets:(.data.targets|length), attention:(.data.attention|length)}'
{
  "status": "fresh",
  "version": "token-radar-v7-candidate-hydration",
  "targets": 5,
  "attention": 5
}
```

## Manual UI Verification

Opened `http://127.0.0.1:8765/?verify=token-radar-ui-kiss` with Playwright after Docker rebuild.

- Initial `1h/all`: Token Radar header showed `TOKEN RADAR 71`.
- After clicking `5m`: Token Radar header showed `TOKEN RADAR 29`.
- Current-page browser console after reload had no warnings or errors.

## Diff Summary

- `web/src/App.tsx` - removed frontend `TOKEN_RADAR_CONTRACT_VERSION` and changed `tokenRadarItems` to gate only on data presence.
- `web/src/App.test.tsx` - added regression coverage and arbitrary projection-version fixture support.
- `docs/superpowers/specs/2026-05-09-token-radar-ui-kiss-contract.md` - documented the KISS boundary.
- `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract.md` - documented the implementation plan and marked tasks complete.
- `docs/superpowers/plans/2026-05-09-token-radar-ui-kiss-contract-verification.md` - captured verification evidence.

## Risks Observed

- Short-window `matched` scope remains empty in current data, while `all` has rows. This change fixes the false frontend empty state for valid API rows; it does not change matched-scope semantics.
- Existing historical search-candidate cleanup remains a separate data-quality topic and is intentionally out of scope for this frontend KISS change.
