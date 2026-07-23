# Verification — Token Radar Content Age and Tape Frontend Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut/plan.md`
**Branch**: `codex/token-radar-content-age-hard-cut`
**Worktree**: `.worktrees/token-radar-content-age-hard-cut/`
**Approved by**: user and GitHub Issue #7
**Approved at**: 2026-07-23

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - One full-height Radar; no frontend Tape, task navigation, or recent read. | Pass | `cd web && npm test -- --run` and the four-viewport Playwright command exited 0. |
| AC2 - Age advances locally and resets on a newer watermark. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with fake-clock and request-count coverage. |
| AC3 - Exact venue/window/scope identity isolation. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with filter-transition coverage. |
| AC4 - Healthy refresh is independent of old or absent content. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with old-content and no-watermark cases. |
| AC5 - Recoverable degradation preserves last-good rows. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with refresh-error and stale/pending cases. |
| AC6 - Initial/fatal/timeout states are unavailable and recover. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with initial failure, failed projection, timeout, clamp, and recovery cases. |
| AC7 - One-second clock has no network/cache side effects and cleans up. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with fake timers, request-count, and unmount coverage. |
| AC8 - Health-only polite announcement. | Pass | `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx` exited 0 with live-region and focus-order assertions. |
| AC9 - React replay zero with notification and market behavior preserved. | Pass | `cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx tests/architecture/liveRadarTapeHardCut.test.ts` exited 0. |
| AC10 - Frontend Tape ownership is hard-deleted. | Pass | `cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx tests/architecture/liveRadarTapeHardCut.test.ts` exited 0. |
| AC11 - Four supported viewport contracts. | Pass | `cd web && npm run test:e2e -- tests/e2e/golden-paths/live-cold-load.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390` exited 0. |
| AC12 - Full gates, backend preservation, docs, and SDD evidence. | Pass | `uv run pytest tests/unit tests/contract -q` and `uv run python scripts/check_sdd_gate.py --feature 2026-07-23-token-radar-content-age-hard-cut --gate verify` exited 0. |

## Verification commands

```text
$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
6 passed in 0.03s
exit code: 0

$ cd web && npm test -- --run tests/routes/live-radar.route.test.tsx
Test Files 1 passed (1)
Tests 8 passed (8)
exit code: 0

$ cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx tests/architecture/liveRadarTapeHardCut.test.ts
Test Files 2 passed (2)
Tests 4 passed (4)
exit code: 0

$ cd web && npm test -- --run
Test Files 72 passed (72)
Tests 293 passed (293)
exit code: 0

$ cd web && npm run lint
ESLint passed with zero warnings.
Architecture Test Files 14 passed (14); Tests 70 passed (70).
exit code: 0

$ cd web && npm run typecheck
TypeScript typecheck passed.
exit code: 0

$ cd web && npm run build
TypeScript typecheck and Vite production build passed; 1926 modules transformed.
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/live-cold-load.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390
15 passed; 9 viewport-inapplicable mobile tests skipped.
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/mobile-route-cold-load.spec.ts tests/e2e/golden-paths/tablet-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390
8 passed; 24 viewport-inapplicable tests skipped.
exit code: 0

$ uv run pytest tests/unit tests/contract -q
2549 passed; 1 opt-in provider-drift test skipped.
exit code: 0

$ uv run pytest -q tests/unit/test_public_event_token_payloads.py tests/integration/test_api_http.py::test_api_bootstrap_exposes_frontend_runtime_config_without_token tests/integration/test_api_http.py::test_api_rejects_protected_reads_without_token tests/integration/test_api_http.py::test_api_exposes_recent_search_and_token_read_models tests/integration/test_cli.py::CliTests::test_recent_search_asset_flow_and_alerts_use_postgres_runtime_store tests/integration/test_cli.py::test_recent_defaults_to_runtime_postgres_store_without_ws_token tests/integration/test_api_websocket.py::test_websocket_auth_subscribe_replay_and_live_filtering tests/integration/test_api_websocket.py::test_websocket_can_subscribe_by_ca_for_replay_and_live_events
11 passed in 132.42s
exit code: 0

$ git diff --check
No whitespace errors.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
SDD work index is current.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-23-token-radar-content-age-hard-cut --gate verify
verify gate passed.
exit code: 0
```

## Deviations

None. Implementation stayed frontend-only and preserved all named backend contracts.

## Risks observed

- The optional live provider-drift contract remains skipped unless
  `GMGN_PROVIDER_DRIFT=1`; this hard cut changes no provider or backend runtime
  path.

## Follow-ups

None for this frontend hard cut.
