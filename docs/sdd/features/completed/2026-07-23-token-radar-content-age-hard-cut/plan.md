# Plan — Token Radar Content Age and Tape Frontend Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-token-radar-content-age-hard-cut/spec.md`
**Worktree**: `.worktrees/token-radar-content-age-hard-cut/`
**Branch**: `codex/token-radar-content-age-hard-cut`
**Approved by**: user and GitHub Issue #7
**Approved at**: 2026-07-23

## Analyze Gate

| Check | Result |
|-------|--------|
| Existing Live route ownership | Pass: `web/src/routes/live.route.tsx` owns recent replay, Tape composition, and Radar composition. |
| Existing Radar query ownership | Pass: `web/src/features/live/api/useTokenRadarQuery.ts` owns the unchanged ten-second HTTP cadence and keep-previous-data behavior. |
| Existing status data | Pass: the generated frontend contract exposes projection identity, status, error, and source watermark. |
| Cache-patch risk | Pass: `web/src/shared/query/patchMarketUpdate.ts` mutates Radar query cache, so query cache update time is excluded from true HTTP success. |
| Socket preservation boundary | Pass: `web/src/shared/socket/IntelSocketProvider.tsx` separately owns notifications, market targets, event buffering, and live-market patches. |
| Backend scope | Pass: no backend source is in the touch set; existing recent, CLI, and public WS replay remain unchanged. |

### Current seams

- `web/src/routes/live.route.tsx` currently owns `/api/recent`, replay/event
  merging, Tape modeling, selection, and Radar composition.
- `web/src/features/live/api/useTokenRadarQuery.ts` owns the ten-second Radar
  HTTP cadence and uses keep-previous-data.
- `web/src/features/live/api/useLiveRadarRouteData.ts` owns query-identity
  parsing and last-ready row preservation.
- `web/src/features/live/ui/TokenRadarTable.tsx` owns the Radar header and
  scan table.
- `web/src/shared/socket/IntelSocketProvider.tsx` owns subscription,
  notification buffering, event buffering, market-target registration, and
  live-market cache patches.
- `web/src/features/live/ui/live.css` owns the Live route desktop/mobile layout,
  including the current Tape and mobile task grid.
- `web/tests/routes/live-radar.route.test.tsx` is the primary behavioral seam;
  `web/tests/component/shared/socket/IntelSocketProvider.test.tsx` is the narrow
  socket seam.

### Ownership decisions

- Extend the existing feature query and route controller; do not add a second
  fetcher or global health store.
- Track real successful HTTP completion inside the Radar query owner, keyed by
  exact window/scope/venue. Do not use React Query `dataUpdatedAt`.
- Derive page-local status from current identity, projection state, last-good
  frame, fetch error, true HTTP completion, and the display clock.
- Keep the query-cache response shape unchanged so live-market patches continue
  to work.
- Put the one-second display clock in the Radar status component/model; it has
  no side effects beyond rerendering.
- Delete frontend Tape and mobile-task files after all consumers are removed.
- Keep backend public event/replay/recent sources untouched.

### Risk analysis

- Keep-previous-data may display the old view while the new request is pending;
  age/health therefore require a separate current-identity match.
- Live-market patches update query data; true HTTP success therefore needs its
  own timestamp.
- React Query background failure may preserve data but expose an error; route
  error presentation must distinguish recoverable cached degradation from
  fatal initial failure.
- The 30-second timeout must continue changing without network traffic, but the
  timer cannot become an implicit poller.
- Mobile reachability depends on removing both the rendered task bar and its
  reserved grid row/padding.

### Test strategy

- Expand the existing Live Radar route integration with controlled HTTP
  responses and fake timers for age, identity, failure, timeout, recovery,
  row preservation, and retired-request assertions.
- Narrow the socket test to subscription replay zero, ignored events, retained
  notifications, market targets, and market-cache patches.
- Add one narrow architecture hard-cut test that scans frontend ownership only.
- Update existing Live Playwright seams for layout, request logs, overflow, and
  final-row reachability at the four supported viewports.
- Run full frontend unit/lint/typecheck after focused tests; run selected
  existing backend recent/WS/CLI tests because the backend contract is
  deliberately unchanged.

## Implementation sequence

1. Add failing route, socket, and architecture expectations.
2. Add exact-identity HTTP-success tracking and Radar freshness view state.
3. Render the two-row non-interactive accessible status header.
4. Collapse Live to a single Radar and hard-delete Tape/recent/mobile-task
   production and test paths.
5. Narrow the shared socket to replay zero with no event storage.
6. Update responsive CSS, Playwright behavior, and canonical frontend docs.
7. Run focused and full gates, audit residual names and requirements, record
   exact evidence, then move the SDD directory to completed.

## Rollback

This is a frontend hard cut. Before release, rollback is the single feature
commit. After release, a product rollback must revert that commit as a unit;
no Tape compatibility wrapper, hidden task mode, dual subscription, or fallback
read will be retained.

## Acceptance test commands

- AC1: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/architecture/liveRadarTapeHardCut.test.ts`
- AC2: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC3: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC4: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC5: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC6: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC7: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC8: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- AC9: `cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx`
- AC10: `cd web && npm test -- --run tests/architecture/liveRadarTapeHardCut.test.ts`
- AC11: `cd web && npm run test:e2e -- tests/e2e/golden-paths/live-cold-load.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390`
- AC12: `uv run python scripts/check_sdd_gate.py --feature 2026-07-23-token-radar-content-age-hard-cut --gate verify`

## Verification commands

```text
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx
cd web && npm test -- --run tests/component/shared/socket/IntelSocketProvider.test.tsx
cd web && npm test -- --run tests/architecture/liveRadarTapeHardCut.test.ts
cd web && npm test -- --run
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run test:e2e -- tests/e2e/golden-paths/live-cold-load.spec.ts tests/e2e/golden-paths/mobile-shell.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390
uv run pytest tests/unit tests/contract -q
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run python scripts/check_sdd_gate.py --feature 2026-07-23-token-radar-content-age-hard-cut --gate verify
git diff --check
```
