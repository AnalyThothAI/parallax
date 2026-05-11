# Spec — Frontend Experience Architecture Hard Cut

**Status**: Implemented
**Date**: 2026-05-11
**Owner**: Codex
**Related**: `docs/superpowers/plans/active/2026-05-11-frontend-experience-architecture-hard-cut.md`

## Background

The frontend contract already defines a layered shape: `web/src/api/` owns HTTP and WebSocket clients, `web/src/domain/` owns pure models, `web/src/store/` bridges push frames into UI state, and `web/src/components/` renders from domain/store state without direct business logic. That rule is documented in `docs/FRONTEND.md:7`.

The current app has outgrown that boundary. `web/src/App.tsx` is 931 lines and still owns bootstrap/status/recent/radar/search/signal-lab/notification queries, selected-signal policy, detail drawer composition, mobile task selection, route definitions, market-update cache patching, and live tape model building. The densest coupling is visible around the query cluster and derived models in `web/src/App.tsx:102`, WebSocket market-target wiring in `web/src/App.tsx:191`, selection effects in `web/src/App.tsx:320`, and route rendering in `web/src/App.tsx:709`.

Signal Lab has already moved to URL routes, but its page component still mixes URL parsing, list querying, watched-account fallback, preferred-candidate auto-navigation, filter mutation, and list/detail layout in one component. The hard-coded page scope/window live in `web/src/components/SignalLabPage.tsx:16`, URL params are parsed in `web/src/components/SignalLabPage.tsx:31`, list/account queries live in `web/src/components/SignalLabPage.tsx:41`, and the auto-redirect to a preferred candidate lives in `web/src/components/SignalLabPage.tsx:78`.

The loading surface is inconsistent. Token Radar has a skeleton in `web/src/components/TokenRadarTable.tsx:92`, timeline has a skeleton in `web/src/components/TokenTimeline.tsx:115`, but Signal Pulse still renders text-only loading in `web/src/components/SignalLabPulse.tsx:48`, Pulse detail renders a generic empty-state loading block in `web/src/components/PulseDetailPage.tsx:11`, watched account events do the same in `web/src/components/SignalLabWorkbench.tsx:168`, and token posts do the same in `web/src/components/TokenPostsPanel.tsx:101`.

The current branch already contains the market-stream recovery path. `web/src/api/useIntelSocket.ts:13` accepts `marketTargets`, `web/src/api/useIntelSocket.ts:74` stores `market_update`, and `web/src/App.tsx:313` patches Token Radar cache entries. The behavior is tested by `web/src/App.test.tsx:213`, but the implementation still lives inside `App.tsx`, not a feature-specific data boundary.

## Problem

The product feels slow and fragile because navigation state, server state, websocket deltas, local interaction state, and rendering decisions are coupled inside page-level components. Users experience this as blank or misleading loading states, direct routes that can show the wrong mobile panel, Signal Lab that jumps unexpectedly from list to detail, and delayed or hard-to-reason-about market updates. Engineers experience it as high blast radius: changing one page requires understanding most of `App.tsx`.

## First Principles

1. **URL owns navigation.** Page identity and shareable filters belong to route params/search params. Zustand must not mirror page navigation fields. This continues the routing discipline described in `docs/superpowers/specs/completed/2026-05-10-frontend-deep-link-routing.md:35`.
2. **React Query owns server state.** API responses stay in React Query cache; WebSocket deltas patch the same cache when they are authoritative and keep polling as reconciliation. This matches the frontend layer rule in `docs/FRONTEND.md:13`.
3. **Zustand owns local cockpit interaction only.** Non-shareable state such as selected detail tab, selected timeline bucket, post sort, and mobile panel may stay local or in store. It must not decide which resource a route renders.
4. **Components render; feature hooks compose; domain/lib transforms.** JSX should not contain cache patching, query orchestration, or model-building logic. Those belong in feature hooks and pure model modules.
5. **No compatibility code.** This hard cut removes route-only fake scoring, preferred-candidate auto-routing, and URL/store double sources. Missing data is shown honestly as missing, not fabricated into a TokenFlowItem.

## Goals

- G1. Reduce `web/src/App.tsx` to a thin app shell of at most 150 lines that contains no query definitions, no selected-signal policy, no market update patching, and no Signal Lab filter logic.
- G2. Make `/`, `/token/:targetType/:targetId`, `/signal-lab`, and `/signal-lab/pulse/:candidateId` directly reloadable on desktop and mobile without rendering a hidden or blank primary panel.
- G3. Give Signal Lab a single route-state owner for `window`, `scope`, `status`, `handle`, and `q`, with route search params as the only source of truth.
- G4. Preserve immediate Token Radar market patching from `/ws market_update` while moving the cache-patch logic out of `App.tsx`.
- G5. Replace text-only loading states on Signal Pulse, Pulse detail, watched account events, and token posts with shared skeleton primitives that preserve layout.
- G6. Split large feature responsibilities into files that can be tested in isolation: live data, live selection, market update patching, Signal Lab route state, Signal Lab list page, Pulse detail route, watchlist rail, and shared UI states.
- G7. Keep current public HTTP/WebSocket contracts unchanged except for consuming the already-defined `market_targets` and `market_update` frontend path.

## Non-goals

- N1. No backend schema, scoring, or Signal Pulse agent changes.
- N2. No new product surfaces beyond stabilizing existing Live, Token Target, Signal Lab, Pulse Detail, Watchlist, and Notifications surfaces.
- N3. No general-purpose design-system migration or UI kit adoption.
- N4. No SSR or route-level code splitting in this pass.
- N5. No score formula changes and no frontend score recomputation.

## Target Architecture

The app becomes a routed cockpit shell with feature modules:

- `app/` owns React Query provider wiring, route definitions, and app shell composition.
- `features/live/` owns live cockpit data, selected signal state, Token Radar market-update cache patching, and live tape model construction.
- `features/signal-lab/` owns Signal Lab route state, list query composition, filter controls, list rendering, and Pulse detail route.
- `features/token-target/` owns token target route parsing and token audit rendering. It shows an honest not-in-current-window state when the route target has timeline/posts data but no current radar row.
- `features/watchlist/` owns watchlist row derivation and rail rendering.
- `features/notifications/` owns notification queries, mutations, drawer state, toast bridge actions, and notification-to-route mapping.
- `shared/ui/` owns skeleton, empty, error, retry, segmented control, and icon-button primitives.
- `shared/query/` owns query key factories so cache patching and query definitions do not rely on repeated string literals.

`App.tsx` only renders the app shell. Feature controllers return typed props for layout, route outlets, and detail panels. They may depend on API hooks and domain models, but presentational components do not call `getApi` directly.

## Conceptual Data Flow

```
HTTP bootstrap/status/recent/token-radar/signal-lab
  → React Query feature hooks
  → pure domain/model transforms
  → feature page components
  → shared layout

/ws event/notification/market_update
  → useIntelSocket
  → feature controllers
  → React Query cache patch or toast/list state
  → render
```

The changed arrows are the last two. Market updates are no longer patched inside `App.tsx`; they flow through a live-feature cache patch module. Signal Lab route search params flow through a Signal Lab route-state module instead of being parsed and mutated inside the page component.

## Core Models

- **CockpitRouteState**: Derived from React Router location. It determines the default mobile task and whether the center route is Live, Token Target, Signal Lab, or Pulse Detail.
- **SignalLabRouteState**: `{ window, scope, status, handle, q }`. Defaults are omitted from the URL; non-default values are serialized. It is the only owner of Signal Lab filters.
- **MarketTargetRef**: `{ target_type, target_id }`, derived from visible Token Radar rows. The WebSocket subscription consumes these refs, and market updates patch matching cache rows by the same tuple.
- **RemoteStateView**: Shared display contract for `loading`, `empty`, `error`, and `stale updating` states. It must preserve panel structure during cold load.
- **SelectedSignal**: Local interaction model for the Live cockpit only. It may select token/event/query for the right detail panel, but it must not select Signal Lab route resources.

## Interface Contracts

HTTP contracts remain the same:

- `/api/token-radar` remains the source of Token Radar rows and `current_market`.
- `/api/signal-lab/pulse` remains the source of Signal Lab list data.
- `/api/signal-lab/pulse/{candidate_id}` remains the source of Pulse detail data.
- `/api/target-social-timeline` and `/api/target-posts` remain the Token Target detail sources.

WebSocket contract remains the same:

- Subscribe may include `market_targets`.
- `market_update` is idempotent by `target_type + target_id + observed_at_ms + provider`.
- The UI patches visible Token Radar rows immediately and keeps HTTP polling for reconciliation.

Routing contract:

- `/` renders Live Radar as primary content.
- `/token/:targetType/:targetId` renders Token Target audit as primary content.
- `/signal-lab` renders the Signal Lab list without auto-navigating to a Pulse detail.
- `/signal-lab/pulse/:candidateId` renders Signal Lab list plus Pulse detail on desktop and a visible Pulse/detail panel on mobile.

## Acceptance Criteria

- AC1. WHEN the browser cold-loads `/signal-lab` on a mobile viewport THEN the Signal Lab list SHALL be visible without requiring the bottom nav.
- AC2. WHEN the browser cold-loads `/signal-lab/pulse/:candidateId` THEN the Pulse detail route SHALL show a skeleton, then detail or in-page not-found, with the Signal Lab shell still visible.
- AC3. WHEN a user edits Signal Lab `status`, `handle`, or `q` THEN the URL query SHALL update and a hard reload SHALL reproduce the same filtered list.
- AC4. WHEN a visible Token Radar row receives a matching `/ws market_update` THEN that row SHALL update `current_market` without waiting for the 10-second HTTP poll.
- AC5. WHEN Live, Signal Pulse, Pulse Detail, watched account events, or Token Posts cold-load THEN they SHALL render skeletons that reserve the final layout shape.
- AC6. WHEN the code is typechecked THEN `App.tsx` SHALL contain no direct `useQuery`, `useMutation`, `getApi`, `useIntelSocket`, `setQueriesData`, or Signal Lab URL parsing.
- AC7. WHEN the test suite runs THEN existing route, notification, Token Radar, Signal Lab, and market update tests SHALL pass with additional regression tests for route-derived mobile state and Signal Lab route-state serialization.
- AC8. WHEN `web/src/styles.css` remains global during this pass THEN new shared states SHALL still be scoped by semantic class names and not add page-specific loading selectors that duplicate another feature.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Large refactor breaks existing interaction flows | High | Red-green tests around route loading, market updates, selected token detail, notification jumps, and Signal Lab filters before moving logic |
| Moving `selectedSignal` changes live detail behavior | High | Keep `SelectedSignal` local to Live feature and preserve existing tests for token/event/query detail |
| Removing Signal Lab auto-redirect changes user expectation | Medium | List page remains stable; Pulse detail still one click away; direct Pulse links remain supported |
| Query cache patch misses paginated or scoped data | Medium | Use query-key factory and patch all matching `token-radar` caches by target tuple |
| Skeletons hide real errors | Medium | Shared query state distinguishes cold loading, stale refetch, empty, and error |
| Virtualization complicates jsdom tests | Low | Do not introduce virtualization until shared state and route ownership are stable; if used, wrap it in one tested shared list primitive |

## Evolution Path

After this hard cut, route-level code splitting can be added at the feature boundary without changing product behavior. A future account profile route can reuse Signal Lab route-state and layout primitives. If watchlist grows large enough to measure render pressure, a single shared virtual-list primitive can be introduced without touching business components.

## Alternatives Considered

- **Move old `App.tsx` into `CockpitRoot.tsx` and call it done.** Rejected because it preserves the coupling under a new filename and does not improve ownership.
- **Adopt a full UI component kit.** Rejected because this app is a dense trading cockpit with custom layout and score semantics; a kit would add visual debt without solving state ownership.
- **Keep Signal Lab preferred-candidate auto-redirect.** Rejected because it makes `/signal-lab` unstable, mutates history on cold load, and hides the list page as a first-class resource.
- **Keep route-only fake TokenFlowItem fallback for token pages.** Rejected because it fabricates scores and undermines the no-black-box/no-fake-score contract.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Route params/search params own page identity and Signal Lab filters. |
| Always | React Query owns HTTP data and is patched by market WebSocket deltas. |
| Always | Cold loading states preserve panel shape with skeletons. |
| Always | Missing current radar row is shown honestly as missing, not scored as zero. |
| Ask first | Introducing virtualization or a third-party UI primitive beyond the current dependency set. |
| Ask first | Changing route paths, score displays, or backend response contracts. |
| Never | Reintroduce Zustand fields for page navigation or Signal Lab filters. |
| Never | Patch market rows in presentational components. |
| Never | Compute or fabricate ranking scores on the frontend. |
