# Spec — Sidebar Navigation Latency Root Fix

**Status**: Draft
**Date**: 2026-05-23
**Owner**: Codex
**Related**: `docs/superpowers/specs/completed/2026-05-22-shadcn-sidebar-navigation-cn.md`, `docs/FRONTEND.md`

## Background

The current app shell uses the shadcn sidebar primitives. `AppSidebar` renders the primary navigation as `Link` / `NavLink` elements under `nav[aria-label="Primary navigation"]`, with route targets defined by `APP_NAVIGATION_GROUPS`; there is no intentional backend dependency in the click handler itself. See `web/src/features/cockpit/ui/AppSidebar.tsx:49`, `web/src/features/cockpit/ui/AppSidebar.tsx:87`, and `web/src/features/cockpit/ui/AppSidebar.tsx:94`.

The sidebar provider owns only open/collapsed UI state, mobile drawer state, cookie persistence, and the `mod+b` shortcut. It does not own app data reads. See `web/src/shared/ui/sidebar.tsx:44`, `web/src/shared/ui/sidebar.tsx:58`, and `web/src/shared/ui/sidebar.tsx:80`.

The shell chrome currently centralizes many server reads in `useShellChromeData`: cockpit status, live recent replay, stocks badge data, news badge data, token radar data, signal lab compact data, socket snapshot merging, and notification controller setup. See `web/src/routes/shellChromeData.ts:82`, `web/src/routes/shellChromeData.ts:83`, `web/src/routes/shellChromeData.ts:89`, `web/src/routes/shellChromeData.ts:95`, `web/src/routes/shellChromeData.ts:99`, `web/src/routes/shellChromeData.ts:105`, `web/src/routes/shellChromeData.ts:123`, and `web/src/routes/shellChromeData.ts:132`.

Route activity already gates some shell reads, but the navigation badge model still keeps route chrome coupled to server data. Token, stocks, and news badge values are derived from query results and passed into the sidebar at `web/src/routes/shellChromeData.ts:117`, `web/src/routes/shellChromeData.ts:118`, `web/src/routes/shellChromeData.ts:120`, and `web/src/routes/shellChromeData.ts:233`.

Notifications are enabled for every route because `shellRouteActivity()` returns `notifications: true`. See `web/src/routes/shellChromeData.ts:270`. `useNotificationsController` fetches `/api/notification-summary` whenever enabled and refetches every 12 seconds. See `web/src/features/notifications/useNotificationsController.ts:38` and `web/src/features/notifications/useNotificationsController.ts:42`. Socket notifications also invalidate notification summary and list queries on every latest notification id change. See `web/src/features/notifications/useNotificationsController.ts:83` and `web/src/features/notifications/useNotificationsController.ts:88`.

The backend notification summary path currently selects every unread notification row and aggregates severity / author counts in Python. See `src/parallax/domains/notifications/repositories/notification_repository.py:318`, `src/parallax/domains/notifications/repositories/notification_repository.py:324`, and `src/parallax/domains/notifications/repositories/notification_repository.py:339`.

The existing desktop sidebar e2e asserts that primary route links are visible and the rail toggle works, but it does not click desktop route links or assert URL transition timing. See `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts:20` and `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts:35`.

Empirical investigation on 2026-05-23 found:

- Mock e2e passed for the existing sidebar visibility / rail toggle flow, so the shadcn primitive is not categorically broken.
- Real data runs showed `docker compose ps` reporting the app container as unhealthy, `/` static route timing out in 3-5 seconds at least once, `/healthz` taking about 2.6 seconds, and `/api/notification-summary` taking about 4.9 seconds in one HTTP sample.
- App logs contained `psycopg.errors.QueryCanceled: canceling statement due to statement timeout` from `routes_notifications.py` through `NotificationRepository.summary()`.
- Running the frontend through Vite while proxying the real API showed coordinate clicks on sidebar links changing the URL only after about 3.1-3.3 seconds.
- Vite later logged proxy failures for `/api/notification-summary`, `/api/status`, `/api/news`, `/api/signal-lab/pulse`, `/api/ops/diagnostics`, and watchlist endpoints when the backend became unavailable.

## Problem

Primary route navigation feels blocked by backend health even though it is a local React Router interaction. Users can click the sidebar and see no immediate route change, delayed changes after several seconds, or failed switching when the backend is overloaded or unavailable.

## First Principles

Navigation is an app-shell control-plane action, not a data-plane action. A route click shall update browser history and visible route shell from already-loaded frontend code without waiting for HTTP, WebSocket, read-model projection, notification summary, or badge freshness.

Kappa/CQRS ownership remains intact: PostgreSQL material facts and read models are the only business truth, and frontend code must not recompute scores, notification rules, or narrative facts locally. `AGENTS.md` states that material facts and derived read models are the business truth, while `docs/FRONTEND.md` says feature API hooks own server reads.

KISS hard cut: remove data dependencies from global navigation instead of adding caches, fallback modes, compatibility wrappers, or parallel legacy paths. The sidebar should answer only "where can I go?"

## Goals

- G1. Desktop and mobile sidebar route clicks update `location.pathname` within 150 ms under mocked API and within 250 ms when real API requests are delayed, failing, or disconnected.
- G2. The sidebar renders without requiring token radar, stocks, news, signal lab, notification, or status query results.
- G3. `/api/notification-summary` returns an aggregated summary from PostgreSQL in one bounded query path, without fetching all unread rows into Python for aggregation.
- G4. Notification summary HTTP reads are not globally hot: they do not run on every route by default, do not refetch every 12 seconds while closed, and socket-triggered invalidation is throttled or replaced by local summary patching.
- G5. Route-specific data reads are owned by the route or feature that renders them; shell chrome does not prefetch heavy route payloads only to show sidebar badges.
- G6. E2E coverage catches the current failure class by clicking desktop sidebar links across at least `News`, `Stocks`, `Signal Lab`, `Ops`, `宏观`, `Watchlist`, and `Token Radar`, then asserting fast URL transition.

## Non-goals

- N1. Do not redesign the visual sidebar, topbar, route pages, Token Radar table, Notification Drawer, or Obsidian components.
- N2. Do not introduce a new background worker, notification read model table, client-side persistence layer, service worker, or broad compatibility shim.
- N3. Do not change notification rule semantics, delivery semantics, unread semantics, or subscriber identity semantics.
- N4. Do not keep old sidebar badge behavior behind a feature flag or "legacy mode."
- N5. Do not make frontend code infer server facts locally to mask backend problems.

## Target Architecture

The sidebar becomes a pure navigation component. It receives static navigation groups and no server-backed badge data. It may render stable labels and route hierarchy only. Active state remains React Router driven.

The shell chrome is split conceptually into:

- Navigation chrome: sidebar links, route outlet, topbar layout, search submit, mobile drawer state.
- Lightweight status chrome: best-effort socket/status/notification UI that can fail independently and never delays navigation.
- Route data: Token Radar, Stocks, News, Signal Lab, Watchlist, Macro, Earnings, Ops, Search, and Token Case fetch only from their owning route / feature entry points.

Notification summary becomes an on-demand or low-frequency topbar concern. The closed bell may show a locally patched best-effort indicator from WebSocket notifications, but it must not force a global polling loop. Opening the drawer fetches fresh summary/list data.

Backend notification summary becomes a small SQL aggregation operation. PostgreSQL returns unread count, high count, critical count, highest severity, and per-author unread counts; Python normalizes the returned aggregate shape only.

## Conceptual Data Flow

Current problematic flow:

```text
sidebar render
  → useShellChromeData
  → route badge queries + notification summary polling + socket invalidations
  → API / PostgreSQL load
  → delayed route click feedback
```

Target flow:

```text
sidebar click
  → React Router history update
  → route shell renders loading/error/empty state
  → route-owned query starts or fails independently
```

Notification flow after this change:

```text
closed bell
  → local socket hint only, no required summary HTTP loop

drawer open
  → /api/notification-summary + /api/notifications
  → render fresh notification state or bounded error state
```

Backend summary flow after this change:

```text
notification tables
  → SQL aggregate query
  → API envelope
  → notification controller
```

No new cross-domain worker or read model is introduced.

## Core Models

Sidebar navigation item:

- `label`: stable user-facing route label.
- `to`: React Router path.
- `matchPath` / `end`: active-state metadata.
- `children`: optional second-level static route links.
- No badge key, server query key, unread count, row count, or mutable data field.

Notification summary:

- `subscriber_key`: subscriber identity for read-state joins.
- `unread_count`: count of unread notifications.
- `high_unread_count`: unread rows with severity `high`.
- `critical_unread_count`: unread rows with severity `critical`.
- `highest_unread_severity`: max severity by `SEVERITY_RANK`, or null when no unread rows exist.
- `account_unread_counts`: author-handle keyed unread counts.

Navigation readiness:

- Route click readiness is binary and local: links are enabled once the React app shell is mounted.
- Backend readiness does not participate in link enabled state.

## Interface Contracts

HTTP `/api/notification-summary` keeps the same external response shape. Its implementation changes from row-fetch-plus-Python-aggregation to SQL aggregation. It returns an empty summary with zero counts when no unread notifications exist.

HTTP route data endpoints keep their current contracts. Their failure states are rendered by owning pages and must not disable or delay sidebar links.

WebSocket notification events remain hints. Receiving a notification may update local UI state or mark cached notification queries stale, but it must not trigger unbounded immediate refetch loops.

No CLI contract changes.

## Acceptance Criteria

- AC1. WHEN any desktop sidebar route link is clicked under mocked API THEN `location.pathname` SHALL change to the target route within 150 ms.
- AC2. WHEN `/api/*` responses are delayed by 5 seconds in an e2e route THEN desktop sidebar route links SHALL still change `location.pathname` within 250 ms.
- AC3. WHEN the backend at `127.0.0.1:8765` is unavailable while the Vite frontend is already loaded THEN sidebar clicks SHALL still navigate between already-loaded route shells instead of waiting for proxy failure.
- AC4. WHEN the app shell renders on `/`, `/stocks`, `/news`, `/macro`, `/watchlist`, `/signal-lab`, `/ops`, or `/search` THEN `AppSidebar` SHALL not receive token/news/stocks badge props derived from server queries.
- AC5. WHEN the notification drawer is closed THEN the frontend SHALL not poll `/api/notification-summary` every 12 seconds.
- AC6. WHEN a WebSocket notification event arrives THEN the frontend SHALL not immediately invalidate both `notification-summary` and `notifications` on every event without throttling or local patching.
- AC7. WHEN `/api/notification-summary` is called with a populated notifications table THEN PostgreSQL SHALL perform aggregation and Python SHALL not iterate over every unread notification row to compute counts.
- AC8. WHEN `/api/notification-summary` is measured against a representative local database with at least 20k notifications and 20k read rows THEN p95 HTTP latency SHALL be below 300 ms while the app is otherwise idle.
- AC9. WHEN route-specific data endpoints fail or time out THEN the currently selected route SHALL show its route-owned error/loading surface and sidebar navigation SHALL remain enabled.
- AC10. WHEN `npm run lint`, `npm run test:architecture`, and the sidebar e2e spec run THEN all SHALL pass without retired CSS buckets, global CSS ownership exceptions, or compatibility routes.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing sidebar badges loses quick count visibility. | Medium | Treat counts as page-level or topbar-local diagnostics, not navigation responsibilities. This is intentional KISS scope reduction. |
| Notification users expect bell counts while drawer is closed. | Medium | Allow best-effort local socket hints, but fresh authoritative counts load on drawer open. |
| SQL aggregation may become complex. | Medium | Keep one repository method and one query path; no new table unless measured SQL cannot meet AC8. |
| Route pages may currently depend on `ShellRouteContext` values produced by shell queries. | High | Move only route-owned reads into existing feature route hooks; keep context for callbacks and local state, not heavy server payload prefetch. |
| E2E timing can be flaky on CI. | Medium | Assert URL transition timing separately from data-loaded UI. Use mocked delayed API to isolate navigation latency from route data latency. |

## Evolution Path

If navigation needs live badges later, add a dedicated lightweight shell-summary endpoint whose explicit contract is "chrome summary only" and whose latency budget is stricter than route data endpoints. Do not reattach heavy route payloads to sidebar rendering.

If notification summary grows beyond simple aggregation, consider a notification summary read model with a single runtime writer. That is out of scope until AC8 cannot be met with a simple aggregate.

## Alternatives Considered

- Keep sidebar badges and add React Query stale caches — rejected because it preserves the coupling between navigation and route data, and it does not address backend unavailability.
- Add a client-side timeout around every shell query — rejected because it is broad compatibility code that hides, rather than removes, the data dependency from navigation.
- Add a notification summary materialized table immediately — rejected because the current requirements can be met with a KISS SQL aggregate first; a table would add writer ownership and rebuild semantics.
- Keep polling `/api/notification-summary` but increase the interval — rejected because closed navigation chrome still should not require notification HTTP polling.
- Patch Playwright tests only — rejected because current failures are observable in real runs and need architectural decoupling plus backend query cleanup.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Sidebar route links are local navigation controls and remain clickable regardless of backend health. |
| Always | Route data loads, errors, and retries belong to the route that renders the data. |
| Always | Notification summary aggregation is bounded and computed by PostgreSQL. |
| Ask first | Reintroducing live sidebar badge counts, adding new read-model tables, or changing notification unread semantics. |
| Never | Block route navigation on `/api/*`, `/ws`, notification summary, status, route badge data, or backend readiness. |
| Never | Add legacy fallback badges, hidden compatibility polling, or frontend recomputation of backend facts. |
