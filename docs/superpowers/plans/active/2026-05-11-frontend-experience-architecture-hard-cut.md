# Plan — Frontend Experience Architecture Hard Cut

**Status**: Implemented
**Date**: 2026-05-11
**Owning spec**: `docs/superpowers/specs/active/2026-05-11-frontend-experience-architecture-hard-cut.md`
**Worktree**: `.worktrees/frontend-experience-architecture-hard-cut/`
**Branch**: `codex/frontend-experience-architecture-hard-cut`

## Pre-flight

- [x] Spec is drafted from the approved audit/design direction.
- [x] Worktree exists at `.worktrees/frontend-experience-architecture-hard-cut/` and `git branch --show-current` is `codex/frontend-experience-architecture-hard-cut`.
- [x] Frontend dependencies installed with `npm install`.
- [x] Baseline `cd web && npm run typecheck` passes.
- [x] Baseline `cd web && npm test -- --run` passes.

Known-failing baseline tests:

- None in the worktree baseline.

## File-level edits

### App shell and route ownership

- Modify `web/src/App.tsx`: reduce to a thin shell that renders `<CockpitApp />` or `<AppRoutes />`; remove direct query definitions, websocket handling, selected-signal policy, notification mutations, route definitions, market patching helpers, and live tape model helpers.
- Create `web/src/app/AppRoutes.tsx`: owns `<Routes>` and maps route paths to feature page components.
- Create `web/src/app/CockpitApp.tsx`: composes layout props from feature controllers and passes route outlets into `CockpitLayout`.
- Create `web/src/app/useRouteMobileTask.ts`: derives route default mobile task from `useLocation()` and keeps local overrides only when they do not conflict with direct deep links.

### Shared UI states

- Create `web/src/shared/ui/RemoteState.tsx`: shared skeleton, empty, error, and loading shell primitives.
- Modify `web/src/components/SignalLabPulse.tsx`: use `SkeletonRows` for cold loading instead of text-only loading.
- Modify `web/src/components/PulseDetailPage.tsx`: use `PanelSkeleton` and `RouteErrorPanel`.
- Modify `web/src/components/SignalLabWorkbench.tsx`: use shared skeletons for watched account event loading and Signal Pulse list loading.
- Modify `web/src/components/TokenPostsPanel.tsx`: use shared skeleton rows for initial post loading.
- Modify `web/src/styles.css`: add shared `.skeleton-*`, `.route-state-panel`, and `.remote-state-*` rules; avoid adding feature-specific duplicate loading selectors.

### Live feature decomposition

- Create `web/src/features/live/liveTapeModel.ts`: move `buildLiveSignalTapeItems`, `tokenTapeBody`, `matchTokenForPayload`, and related pure helpers out of `App.tsx`.
- Create `web/src/features/live/marketUpdatePatch.ts`: move `patchTokenRadarMarketUpdate`, `patchAssetFlowData`, and matching helpers out of `App.tsx`.
- Create `web/src/features/live/useLiveData.ts`: owns bootstrap/status/recent/token-radar compact Signal Pulse queries, `useIntelSocket`, live item merge, token item derivation, market-target derivation, market update patch effect, decision counts, and watchlist rows.
- Create `web/src/features/live/useLiveSelection.ts`: owns `SelectedSignal`, selected tape id, token detail tab/window/mode, post filters, selected bucket/event, and handlers for token/tape/account/query selection.
- Modify `web/src/components/LivePage.tsx` and `web/src/components/LiveRadar.tsx` only as needed for prop naming; keep presentational behavior stable.

### Signal Lab hard cut

- Create `web/src/features/signal-lab/signalLabRouteState.ts`: parse and serialize `window`, `scope`, `status`, `handle`, and `q`; omit defaults from the URL.
- Create `web/src/features/signal-lab/useSignalLabPage.ts`: owns Signal Lab list query, account lens query, merged pages, selected pulse id from route, and filter update callbacks.
- Modify `web/src/components/SignalLabPage.tsx`: turn into a presentational page shell that receives controller props; remove direct `getApi`, `useQuery`, `useSignalPulseList`, `useSearchParams`, and auto-redirect.
- Modify `web/src/components/SignalLabWorkbench.tsx`: accept shared route state and use clear list/pulse empty states.
- Modify `web/src/components/PulseDetailPage.tsx`: keep direct candidate query, but no dependency on list preloading.

### Token Target honesty pass

- Modify `web/src/components/TokenTargetPage.tsx`: remove `fallbackTokenItemFromTarget()` and related `routeOnlyScoreBlock()` helpers.
- Add an honest not-in-current-window state when the route target has no matching current radar row, while timeline/posts loading may still proceed.
- Keep score audit rendering only when a real `TokenFlowItem` exists.

### Notifications and Watchlist

- Create `web/src/features/notifications/useNotificationsController.ts`: move notification queries, mark-read mutations, drawer state, socket invalidation, and notification-to-route mapping out of `App.tsx`.
- Create `web/src/features/watchlist/WatchlistRail.tsx`: move desktop watchlist rail rendering out of `CockpitLayout` if layout prop count stays too high.
- Keep `web/src/lib/watchlist.ts` as the pure watchlist row builder; do not add route or React dependencies there.

### Query keys and contracts

- Create `web/src/shared/query/queryKeys.ts`: define query key factories for bootstrap, status, recent, token radar, Signal Lab, notification summary, notifications, account quality, target timeline, and target posts.
- Update feature hooks to use query key factories.
- Keep public API payload types in `web/src/api/types.ts`; do not split the type file in this pass unless TypeScript edits require it.

### Tests

- Add `web/src/features/signal-lab/signalLabRouteState.test.ts`:
  - parses omitted params to defaults;
  - serializes non-default params;
  - normalizes `@handle` to handle form;
  - rejects invalid window/scope/status to defaults.
- Add `web/src/features/live/marketUpdatePatch.test.ts`:
  - patches a matching target row;
  - leaves non-matching rows referentially stable;
  - patches all matching `token-radar` query caches.
- Add or update App routing tests:
  - cold `/signal-lab` shows Lab nav active and list shell visible;
  - cold `/signal-lab/pulse/:candidateId` shows detail shell visible;
  - mobile route default does not hide the active route panel.
- Update existing tests only when behavior intentionally changes, such as removing Signal Lab auto-redirect.

## PR Breakdown

1. **PR 1 — Shared State and Pure Modules**
   - Add shared UI state primitives.
   - Extract `marketUpdatePatch` and `liveTapeModel`.
   - Add focused unit tests for pure modules.
   - Mergeable on its own because behavior remains stable.

2. **PR 2 — Signal Lab Route Ownership**
   - Add `signalLabRouteState`.
   - Refactor `SignalLabPage` into controller + presentational shell.
   - Remove preferred-candidate auto-redirect.
   - Add route-state and direct-load tests.

3. **PR 3 — App Shell Decomposition**
   - Add app route shell and live/notification controllers.
   - Reduce `App.tsx` below 150 lines.
   - Preserve existing App integration behavior.

4. **PR 4 — Token Target Honesty and Loading Polish**
   - Remove route-only fake TokenFlowItem fallback.
   - Add honest not-in-current-window state.
   - Replace remaining text-only loading states with shared skeletons.

This worktree may implement these PR slices in one branch, but the diff should stay reviewable in the same order.

## Rollout Order

1. Merge frontend-only refactor after `cd web && npm test -- --run && npm run build` pass.
2. Run manual browser verification for `/`, `/signal-lab`, `/signal-lab/pulse/:candidateId`, and `/token/:targetType/:targetId` on desktop and mobile viewports.
3. Keep backend market-update publishing unchanged; frontend still has HTTP polling reconciliation.
4. If manual live WebSocket verification cannot be performed because local backend is unavailable, record the gap in verification and rely on mocked WebSocket tests.

## Rollback

- Revert the frontend branch. No migration or backend rollback is needed.
- If Signal Lab list stability surprises users, the route still supports Pulse detail links; do not restore auto-redirect. Instead add an explicit “open top candidate” affordance in a follow-up.
- If market-update patching regresses, disable only the frontend market-update effect and rely on the existing 10-second HTTP polling until fixed.

## Acceptance Test Commands

- AC1, AC2, AC3: `cd web && npm test -- --run src/components/__tests__/SignalLabPage.routing.test.tsx src/components/__tests__/PulseDetailPage.routing.test.tsx`
- AC4: `cd web && npm test -- --run src/App.test.tsx -t "patches visible token-radar rows with websocket market updates"`
- AC5: `cd web && npm test -- --run src/components/SignalLabPulse.test.tsx src/components/NotificationCenter.test.tsx`
- AC6: `cd web && npm run typecheck` plus source scan:
  `rg -n "useQuery|useMutation|getApi|useIntelSocket|setQueriesData|useSearchParams" web/src/App.tsx`
- AC7: `cd web && npm test -- --run`
- Build gate: `cd web && npm run build`

## Verification

Record final verification in this plan before declaring completion:

- [x] `cd web && npm run typecheck`
- [x] `cd web && npm test -- --run`
- [x] `cd web && npm run build`
- [x] Browser desktop smoke for `/`, `/signal-lab`, `/signal-lab/pulse/:candidateId`, `/token/:targetType/:targetId`
- [x] Browser mobile smoke for `/signal-lab` and `/signal-lab/pulse/:candidateId`
- [x] Remaining risks documented

## Implementation Notes

- `web/src/App.tsx` is now a 5-line entry shell; app composition lives in `web/src/app/CockpitApp.tsx`.
- Signal Lab URL state lives in `web/src/features/signal-lab/signalLabRouteState.ts`; `SignalLabPage` delegates URL/query behavior to `useSignalLabPage`.
- Live data, live selection, live tape modeling, market-update patching, notifications, and token detail data now live in feature modules instead of `App.tsx`.
- Token Target no longer fabricates route-only score blocks. Missing current-window radar rows render an honest not-in-current-window state and suppress score audit.
- Browser smoke used the Vite dev server only; backend API was not running, so console errors were expected `/api/bootstrap` proxy failures to `127.0.0.1:8765`. Route shells still rendered without blank panels.
- Query-key factories and a separate watchlist rail component remain follow-up cleanup; current keys stayed local to the new feature hooks to keep this refactor behavior-preserving.
