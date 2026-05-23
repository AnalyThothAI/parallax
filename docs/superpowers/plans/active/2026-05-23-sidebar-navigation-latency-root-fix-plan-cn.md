# Sidebar Navigation Latency Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sidebar route switching a local, immediate React Router action that is not delayed by API, WebSocket, notification summary, route badge data, or backend health.

**Architecture:** Hard-cut server-backed navigation chrome. Move heavy route data reads out of `useShellChromeData`, make notifications on-demand while closed, and aggregate notification summary in PostgreSQL. Add regression tests that delay or fail API calls while asserting URL changes immediately.

**Tech Stack:** React 19, React Router 6, TanStack Query 5, Vite, Playwright, Vitest/RTL/MSW, FastAPI, psycopg/PostgreSQL.

---

## Root Review

This can solve the root cause if implementation preserves the key invariant: route links must not depend on data query completion. The current spec is strong because it removes the coupling rather than adding timeouts or caches.

The highest-risk partial fix would be optimizing `/api/notification-summary` only. That would make the current machine feel better but leave `useShellChromeData` able to create the next navigation stall through route badge queries, status polling, signal compact reads, or future shell data additions. The plan below therefore tests local URL transition first, then removes shell data dependencies, then optimizes the known backend hotspot.

The second risk is preserving old sidebar badges as a hidden compatibility path. Do not keep `badgeKey`, `AppSidebarBadges`, or server-derived badge props. If live counts are useful later, they need a separate lightweight chrome-summary contract, not route payload reuse.

The third risk is moving too much at once. The KISS line is: keep existing route pages and feature hooks; move route-owned reads to the route that renders them; do not introduce stores, service workers, new read-model tables, or feature flags.

## File Map

- Modify `web/src/routes/shellChromeData.ts`: keep only shell-local state, token, scope/window URL state, search callbacks, mobile task callbacks, best-effort notification controller, and topbar status. Remove token radar, recent replay, stocks badge, news badge, signal lab compact, live tape, market targets, and sidebar badge derivation from this hook.
- Modify `web/src/routes/live.route.tsx`: own live-only data reads (`useLiveRecentQuery`, `useLiveRadarRouteData`, `useSignalLabCompactQuery`), live tape construction, market target subscription, and `LivePage` data props.
- Modify `web/src/routes/signal-lab.route.tsx`: stop receiving shell-provided `overviewData`; let `SignalLabPage` use its feature-owned query path.
- Modify `web/src/routes/watchlist.route.tsx`: stop depending on notification summary account counts from shell while the drawer is closed; pass no account unread counts unless a future dedicated watchlist source owns them.
- Modify `web/src/features/cockpit/ui/appNavigation.ts`: remove `badgeKey` from navigation items.
- Modify `web/src/features/cockpit/ui/AppSidebar.tsx`: remove `badges`, `AppSidebarBadges`, `SidebarMenuBadge`, and `compactNumber` usage.
- Modify `web/src/features/cockpit/ui/CockpitShell.tsx` and `web/src/features/cockpit/ui/SearchShell.tsx`: pass `AppSidebar` without badge props.
- Modify `web/src/features/cockpit/ui/CockpitTopbar.tsx`: remove server-derived `stats` prop and top-stats values that depended on route data. Keep search, status, ops, notifications, and refresh controls.
- Modify `web/src/features/notifications/useNotificationsController.ts`: fetch summary/list only when drawer is open or after explicit mutation actions; no closed-drawer 12s polling; no unthrottled socket invalidation loop while closed.
- Modify `web/src/features/notifications/ui/NotificationBell.tsx`: accept a best-effort local unread hint through the same `summary` prop shape; display no count when there is no local hint or loaded summary.
- Modify `src/gmgn_twitter_intel/domains/notifications/repositories/notification_repository.py`: replace Python row aggregation in `summary()` with SQL aggregate queries.
- Modify `tests/integration/test_notification_repository.py`: add coverage proving summary remains correct and uses aggregate SQL shape.
- Modify `tests/integration/test_api_http.py`: keep existing API summary contract coverage; add high/critical/author count assertion if missing.
- Modify `web/tests/routes/live-radar.route.test.tsx`: replace badge expectation with pure navigation expectation.
- Modify `web/tests/routes/notifications.route.test.tsx`: assert closed bell does not fetch summary, opening drawer fetches summary/list, and socket events do not cause closed-drawer summary invalidation.
- Modify `web/tests/e2e/support/mockApi.ts`: allow delayed or failing non-bootstrap API calls.
- Modify `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts`: add desktop route-click tests for normal, delayed API, and failed API modes.

## Task 0: Worktree Setup

**Files:**
- No source edits.

- [ ] **Step 1: Create an isolated worktree**

Run from repository root:

```bash
git worktree add .worktrees/sidebar-navigation-latency-root-fix -b codex/sidebar-navigation-latency-root-fix main
cd .worktrees/sidebar-navigation-latency-root-fix
```

Expected: worktree created on `codex/sidebar-navigation-latency-root-fix`.

- [ ] **Step 2: Verify worktree state**

Run:

```bash
git worktree list
git status --short
git branch --show-current
```

Expected: branch is `codex/sidebar-navigation-latency-root-fix`; no unrelated local edits are present in the worktree.

## Task 1: Sidebar Navigation Regression Tests

**Files:**
- Modify: `web/tests/e2e/support/mockApi.ts`
- Modify: `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts`

- [ ] **Step 1: Extend the mock API helper with delay/failure controls**

In `web/tests/e2e/support/mockApi.ts`, change the helper signature and insert the non-bootstrap delay/failure branch immediately after `const path = url.pathname;`:

```ts
type MockApiOptions = {
  delayNonBootstrapMs?: number;
  failNonBootstrap?: boolean;
};

export async function installMockApi(page: Page, options: MockApiOptions = {}) {
  unhandledApiRequests.set(page, []);

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path !== "/api/bootstrap" && options.delayNonBootstrapMs) {
      await page.waitForTimeout(options.delayNonBootstrapMs);
    }

    if (path !== "/api/bootstrap" && options.failNonBootstrap) {
      return route.abort("failed");
    }
```

Leave the existing `/api/bootstrap` handler and all existing route handlers unchanged below this insertion.

- [ ] **Step 2: Add a desktop route click timing helper**

In `web/tests/e2e/golden-paths/sidebar-navigation.spec.ts`, add this helper below the imports:

```ts
async function expectSidebarRouteClickFast(
  page: import("@playwright/test").Page,
  routeName: string,
  expectedPath: RegExp,
  budgetMs = 250,
) {
  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  const startedAt = Date.now();
  await primaryNavigation.getByRole("link", { name: routeName, exact: true }).click();
  await expect(page).toHaveURL(expectedPath);
  expect(Date.now() - startedAt).toBeLessThanOrEqual(budgetMs);
}
```

- [ ] **Step 3: Add normal desktop route-click coverage**

In the desktop `describe`, add a new test:

```ts
test("switches desktop routes from the sidebar without waiting for route data", async ({ page }) => {
  await installMockApi(page);
  await page.goto("/");

  await expectSidebarRouteClickFast(page, "News", /\/news(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Stocks", /\/stocks(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Token Radar", /\/(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Signal Lab", /\/signal-lab(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Ops", /\/ops(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "宏观", /\/macro(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Watchlist", /\/watchlist(?:\?|$)/, 250);

  await expectNoDocumentHorizontalOverflow(page);
  await expectNoUnhandledApiRequests(page);
});
```

- [ ] **Step 4: Add delayed API route-click coverage**

Add this test in the same desktop `describe`:

```ts
test("keeps desktop sidebar navigation instant while API requests are delayed", async ({ page }) => {
  await installMockApi(page, { delayNonBootstrapMs: 5_000 });
  await page.goto("/");

  await expectSidebarRouteClickFast(page, "News", /\/news(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Stocks", /\/stocks(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Signal Lab", /\/signal-lab(?:\?|$)/, 250);
});
```

- [ ] **Step 5: Add failed API route-click coverage**

Add this test in the same desktop `describe`:

```ts
test("keeps desktop sidebar navigation available when route APIs fail", async ({ page }) => {
  await installMockApi(page, { failNonBootstrap: true });
  await page.goto("/");

  await expectSidebarRouteClickFast(page, "News", /\/news(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Ops", /\/ops(?:\?|$)/, 250);
  await expectSidebarRouteClickFast(page, "Token Radar", /\/(?:\?|$)/, 250);
});
```

- [ ] **Step 6: Run the new e2e and verify it fails before implementation**

Run:

```bash
cd web && npm run test:e2e -- --project=desktop-1366 tests/e2e/golden-paths/sidebar-navigation.spec.ts --reporter=line
```

Expected before implementation: at least one new desktop route-click timing assertion fails or the failed/delayed API case exposes existing shell coupling.

- [ ] **Step 7: Commit failing tests**

```bash
git add web/tests/e2e/support/mockApi.ts web/tests/e2e/golden-paths/sidebar-navigation.spec.ts
git commit -m "test: cover sidebar route latency under api delay"
```

## Task 2: Hard-Cut Server Data From Sidebar And Shell Chrome

**Files:**
- Modify: `web/src/features/cockpit/ui/appNavigation.ts`
- Modify: `web/src/features/cockpit/ui/AppSidebar.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitShell.tsx`
- Modify: `web/src/features/cockpit/ui/SearchShell.tsx`
- Modify: `web/src/features/cockpit/ui/CockpitTopbar.tsx`
- Modify: `web/src/routes/shellChromeData.ts`
- Modify: `web/src/routes/live.route.tsx`
- Modify: `web/src/routes/signal-lab.route.tsx`
- Modify: `web/src/routes/watchlist.route.tsx`
- Modify: `web/tests/routes/live-radar.route.test.tsx`
- Modify: `web/tests/component/features/cockpit/ui/CockpitTopbar.test.tsx`

- [ ] **Step 1: Remove navigation badge metadata**

In `web/src/features/cockpit/ui/appNavigation.ts`, remove `AppNavigationBadgeKey` and the optional `badgeKey` property from `AppNavigationItem`. Remove `badgeKey` assignments from `Token Radar`, `Stocks`, and `News`.

Expected item shape:

```ts
export type AppNavigationItem = {
  children?: AppNavigationItem[];
  end?: boolean;
  icon?: LucideIcon;
  label: string;
  matchPath?: string;
  to: string;
};
```

- [ ] **Step 2: Remove badge rendering from `AppSidebar`**

In `web/src/features/cockpit/ui/AppSidebar.tsx`, remove `compactNumber`, `SidebarMenuBadge`, `AppSidebarBadges`, `badges`, `badgeForItem`, and the badge prop on `AppSidebarItem`.

Expected top-level component:

```tsx
export function AppSidebar() {
  return (
    <Sidebar
      className="cockpit-app-sidebar"
      collapsible="icon"
      variant="sidebar"
      aria-label="Application sidebar"
    >
      <SidebarHeader className="cockpit-app-sidebar-header">
        <div className="cockpit-app-sidebar-brand">
          <span className="cockpit-app-sidebar-mark" aria-hidden />
          <span>
            <b>gmgn.intel</b>
            <small>obsidian desk</small>
          </span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Primary navigation" className="cockpit-app-sidebar-nav">
          {APP_NAVIGATION_GROUPS.map((group) => (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel asChild>
                <h2 className="cockpit-app-sidebar-group-heading">{group.label}</h2>
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((item) => (
                    <AppSidebarItem item={item} key={item.to} />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter className="cockpit-app-sidebar-footer">
        <div aria-label="Desk status" className="cockpit-app-sidebar-status" role="status">
          <span className="cockpit-app-sidebar-status-dot" aria-hidden />
          <span className="cockpit-app-sidebar-status-copy">
            <strong>Live desk</strong>
            <small>facts online</small>
          </span>
        </div>
      </SidebarFooter>
      <SidebarRail className="cockpit-app-sidebar-rail" />
    </Sidebar>
  );
}
```

Expected item signature:

```tsx
function AppSidebarItem({ item }: { item: AppNavigationItem }) {
```

- [ ] **Step 3: Remove sidebar badge props from shell components**

In `web/src/features/cockpit/ui/CockpitShell.tsx`, remove `AppSidebarBadges` import and the `sidebar` field from `CockpitShellProps`. Render `<AppSidebar />`.

Expected prop type starts:

```ts
export type CockpitShellProps = {
  topbar: CockpitTopbarProps;
  notifications: ShellNotificationProps;
  onHotkey: (event: KeyboardEvent) => void;
  outletContext?: unknown;
};
```

In `web/src/features/cockpit/ui/SearchShell.tsx`, mirror the same prop removal if it accepts `sidebar`.

- [ ] **Step 4: Remove route-data topbar stats**

In `web/src/features/cockpit/ui/CockpitTopbar.tsx`, remove the `stats` prop and delete the `<div className="top-stats">...</div>` block that renders flow/trade/token/risk counts. Keep search, status pills, ops button, notification bell, and refresh button.

Update `web/tests/component/features/cockpit/ui/CockpitTopbar.test.tsx` to remove `stats` from test props and remove assertions for top-stats text.

- [ ] **Step 5: Shrink `ShellRouteContext` to shell-local state**

In `web/src/routes/shellChromeData.ts`, remove imports and hook calls for:

```ts
buildLiveSignalTapeItems
useLiveRadarRouteData
useLiveRecentQuery
NEWS_PAGE_SIZE
useNewsPageWithToken
useSignalLabCompactQuery
useStocksRadarQuery
MarketTargetRef
LivePayload
SignalPulseData
TokenFlowItem
LiveSignalTapeItem
```

Keep `useLiveRouteState`, `useLiveSelection`, `useCockpitStatusQuery`, `useNotificationsController`, `useSocketSnapshot`, `useQueryClient`, `useMemo`, `useRef`, and `useLocation`.

Update `ShellRouteContext` to:

```ts
export type ShellRouteContext = {
  configuredWatchlistHandles: string[];
  mobileTask: LiveMobileTask;
  onMarkHandleRead: (handle: string) => void;
  scope: ScopeKey;
  selectedAccountEventId: string | null;
  selectedPulseItemId: string | null;
  selectedTapeEventId: string | null;
  selectAccountEvent: (item: LivePayload) => void;
  selectPulseItem: (item: SignalPulseItem) => void;
  selectToken: (item: TokenFlowItem) => void;
  socketStatus: string;
  token: string;
  updateScope: (scope: ScopeKey) => void;
  updateWindow: (window: WindowKey) => void;
  windowKey: WindowKey;
  liveRouteHandles: string[];
  onMobileTaskChange: (task: LiveMobileTask) => void;
  onTapeSelect: (item: LiveSignalTapeItem) => void;
};
```

Keep the type imports for `LivePayload`, `SignalPulseItem`, `TokenFlowItem`, and `LiveSignalTapeItem` because callbacks still use them.

- [ ] **Step 6: Build shell props without heavy queries**

In `useShellChromeData`, compute:

```ts
const statusQuery = useCockpitStatusQuery({ token: session.token });
const socketSnapshot = useSocketSnapshot();
const searchInputRef = useRef<HTMLInputElement | null>(null);
const bootstrapHandles = session.bootstrapHandles;
const scope = liveRoute.scope;
const status = statusQuery.data?.data ?? null;
const token = session.token;
const windowKey = liveRoute.window;
const selection = useLiveSelection({ scope });
const notificationsController = useNotificationsController({
  enabled: true,
  fallbackSummary: null,
  prefetchList: false,
  setMobileTask: selection.setMobileTask,
  socketNotifications: socketSnapshot.notificationItems,
  token,
});
```

Set `configuredWatchlistHandles` from bootstrap only:

```ts
const configuredWatchlistHandles = bootstrapHandles;
```

Set `topbarProps` without `stats`:

```ts
const topbarProps = {
  search: {
    inputRef: searchInputRef,
    onSubmitQuery: selection.submitEvidenceSearch,
  },
  status: {
    socketStatus: socketSnapshot.status,
    lastSocketMessageAt: socketSnapshot.lastMessageAt,
    status,
    statusLoading: Boolean(token) && statusQuery.isPending,
    statusError: statusQuery.isError,
    configReady: Boolean(token),
  },
  notifications: {
    summary: notificationsController.notificationSummary,
    drawerOpen: notificationsController.drawerOpen,
    onToggleDrawer: notificationsController.toggleDrawer,
  },
  onRefresh: () => void queryClient.invalidateQueries(),
};
```

Set `shellProps` without `sidebar`:

```ts
const shellProps = {
  notifications: notificationProps,
  topbar: topbarProps,
  onHotkey: handleHotkey,
  outletContext: routeContext,
};
```

- [ ] **Step 7: Move live route data reads into `live.route.tsx`**

In `web/src/routes/live.route.tsx`, import:

```ts
import {
  buildLiveSignalTapeItems,
  useLiveRadarRouteData,
  useLiveRecentQuery,
} from "@features/live/shell";
import { useSignalLabCompactQuery } from "@features/signal-lab/shell";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import { useMemo } from "react";
```

Inside `Component`, after `const context = useShellRouteContext();`, add:

```ts
const recentQuery = useLiveRecentQuery({
  enabled: true,
  handles: context.liveRouteHandles,
  scope: context.scope,
  token: context.token,
});
const liveRadar = useLiveRadarRouteData({
  enabled: true,
  scope: context.scope,
  token: context.token,
  window: context.windowKey,
});
const signalLabCompact = useSignalLabCompactQuery({
  enabled: true,
  token: context.token,
});
const socketSnapshot = useSocketSnapshot();
const recentReplayItems = recentQuery.data?.data.items ?? [];
const liveItems = useMemo(
  () => mergeLiveItems(recentReplayItems, socketSnapshot.eventItems),
  [recentReplayItems, socketSnapshot.eventItems],
);
const liveSignalTapeItems = useMemo(
  () => buildLiveSignalTapeItems({ liveItems, tokenItems: liveRadar.tokenItems }),
  [liveItems, liveRadar.tokenItems],
);
```

Add `mergeLiveItems` at the bottom of `live.route.tsx`:

```ts
function mergeLiveItems(replayItems: LivePayload[], eventItems: LivePayload[]): LivePayload[] {
  const byId = new Map<string, LivePayload>();
  for (const item of [...replayItems, ...eventItems]) {
    byId.set(item.event.event_id, item);
  }
  return [...byId.values()].sort(
    (left, right) =>
      Number(right.event.received_at_ms ?? 0) - Number(left.event.received_at_ms ?? 0),
  );
}
```

Update `LivePage` props to use live-route-owned data:

```tsx
<LivePage
  hiddenSignalLabPulseData={signalLabCompact.hiddenSignalPulseData}
  hiddenSignalPulseLoading={signalLabCompact.hiddenSignalPulseLoading}
  isRecentLoading={recentQuery.isPending}
  liveSignalTapeItems={liveSignalTapeItems}
  mobileTask={context.mobileTask}
  selectedPulseItemId={context.selectedPulseItemId}
  selectedTapeEventId={context.selectedTapeEventId}
  signalLabPulseData={signalLabCompact.pulseData ?? null}
  signalPulseLoading={signalLabCompact.signalPulseColdLoading}
  socketStatus={socketSnapshot.status}
  onMobileTaskChange={context.onMobileTaskChange}
  onSelectPulse={context.selectPulseItem}
  onTapeSelect={context.onTapeSelect}
>
  <LiveMarketSubscription targets={liveRadar.marketTargets}>
    <LiveRadar
      assetFlowError={liveRadar.assetFlowError}
      isAssetFlowLoading={liveRadar.isAssetFlowLoading}
      isAssetFlowRefreshing={liveRadar.isAssetFlowRefreshing}
      scope={context.scope}
      selectedTokenKey={null}
      tokenItems={liveRadar.tokenItems}
      windowKey={context.windowKey}
      onScopeChange={context.updateScope}
      onSelectToken={context.selectToken}
      onWindowChange={context.updateWindow}
    />
  </LiveMarketSubscription>
</LivePage>
```

- [ ] **Step 8: Remove shell-provided Signal Lab and Watchlist data**

In `web/src/routes/signal-lab.route.tsx`, remove `overviewData={context.signalLabOverviewData}`.

In `web/src/routes/watchlist.route.tsx`, remove `accountUnreadCounts={context.accountUnreadCounts}`.

- [ ] **Step 9: Update route tests for the hard cut**

In `web/tests/routes/live-radar.route.test.tsx`, replace `shows sidebar badges for primary market destinations` with:

```ts
it("keeps primary navigation free of server-backed badges", async () => {
  renderAppRoute("/");

  const navigation = await screen.findByRole("navigation", { name: "Primary navigation" });

  expect(within(navigation).getByRole("link", { name: /Token Radar/i })).toBeInTheDocument();
  expect(within(navigation).getByRole("link", { name: /Stocks/i })).toBeInTheDocument();
  expect(within(navigation).getByRole("link", { name: /News/i })).toBeInTheDocument();
  expect(within(navigation).queryByText("2")).not.toBeInTheDocument();
  expect(within(navigation).queryByText("2+")).not.toBeInTheDocument();
});
```

- [ ] **Step 10: Run route/topbar tests**

Run:

```bash
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/component/features/cockpit/ui/CockpitTopbar.test.tsx
```

Expected: tests pass after shell data is hard-cut.

- [ ] **Step 11: Run delayed sidebar e2e**

Run:

```bash
cd web && npm run test:e2e -- --project=desktop-1366 tests/e2e/golden-paths/sidebar-navigation.spec.ts --reporter=line
```

Expected: desktop route-click tests pass, including delayed and failed API cases.

- [ ] **Step 12: Commit shell hard cut**

```bash
git add web/src web/tests
git commit -m "fix: decouple sidebar navigation from route data"
```

## Task 3: Make Notifications On-Demand While Closed

**Files:**
- Modify: `web/src/features/notifications/useNotificationsController.ts`
- Modify: `web/tests/routes/notifications.route.test.tsx`

- [ ] **Step 1: Add closed-drawer no-summary test**

In `web/tests/routes/notifications.route.test.tsx`, add:

```ts
it("does not fetch notification summary before the drawer opens", async () => {
  renderAppRoute("/");

  await screen.findByRole("button", { name: "notifications" });

  expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
    false,
  );
  expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(false);
});
```

- [ ] **Step 2: Update existing drawer test to assert fetch-on-open**

Change the existing test to click first, then wait for count:

```ts
it("fetches notifications only after opening the drawer", async () => {
  renderAppRoute("/");

  const bell = await screen.findByRole("button", { name: "notifications" });
  expect(bell).not.toHaveTextContent("1");

  fireEvent.click(bell);

  expect(
    await screen.findByRole("complementary", { name: "notification drawer" }),
  ).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("1 unread")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "open Signal Pulse" })).toBeInTheDocument();
  expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
    true,
  );
  expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notifications")).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "close notifications" }));
  expect(screen.queryByRole("complementary", { name: "notification drawer" })).toBeNull();
});
```

- [ ] **Step 3: Add socket invalidation test while closed**

Import `socketScenario`:

```ts
import { socketScenario } from "@tests/socket/socketScenarios";
```

Add test:

```ts
it("does not refetch summary for socket notifications while the drawer is closed", async () => {
  socketScenario.notifications = [
    {
      type: "notification",
      notification: {
        notification_id: "socket-notification-1",
        rule_id: "signal_pulse_candidate",
        severity: "high",
        title: "Signal Pulse",
        body: "candidate ready",
        entity_type: "pulse_candidate",
        entity_key: "pulse:candidate",
        author_handle: "traderpow",
        symbol: "PEPE",
        chain: "eth",
        address: null,
        event_id: "event-1",
        source_table: "pulse_candidates",
        source_id: "candidate-1",
        occurrence_count: 1,
        first_seen_at_ms: 1_700_000_000_000,
        last_seen_at_ms: 1_700_000_000_000,
        created_at_ms: 1_700_000_000_000,
        updated_at_ms: 1_700_000_000_000,
        read_at_ms: null,
        payload: {},
        channels: ["in_app"],
      },
    },
  ];

  renderAppRoute("/");

  const bell = await screen.findByRole("button", { name: "notifications" });
  expect(bell).toHaveTextContent("1");
  expect(apiMock.getApi.mock.calls.some(([path]) => path === "/api/notification-summary")).toBe(
    false,
  );
});
```

- [ ] **Step 4: Run tests to verify failure before implementation**

Run:

```bash
cd web && npm test -- --run tests/routes/notifications.route.test.tsx
```

Expected before implementation: at least the closed-drawer no-summary test fails because summary currently fetches on mount.

- [ ] **Step 5: Change summary/list queries to drawer-open only**

In `web/src/features/notifications/useNotificationsController.ts`, change the query setup:

```ts
const summaryQuery = useQuery({
  queryKey: queryKeys.notificationSummary(),
  queryFn: () => getNotificationSummary(token),
  enabled: Boolean(token) && enabled && drawerOpen,
});

const notificationsQuery = useQuery({
  queryKey: queryKeys.notifications(),
  queryFn: () => getNotifications(token),
  enabled: Boolean(token) && enabled && drawerOpen,
});
```

Remove `prefetchList` from `UseNotificationsControllerArgs` and from all call sites.

- [ ] **Step 6: Replace closed socket invalidation with local summary hint**

Add a helper at the bottom of `useNotificationsController.ts`:

```ts
function summaryFromSocketNotifications(
  socketNotifications: NotificationLivePayload[],
): NotificationSummary | null {
  if (!socketNotifications.length) {
    return null;
  }
  const accountUnreadCounts: Record<string, number> = {};
  let highUnreadCount = 0;
  let criticalUnreadCount = 0;
  let highestUnreadSeverity: NotificationSummary["highest_unread_severity"] = null;
  for (const item of socketNotifications) {
    const notification = item.notification;
    if (notification.read_at_ms) {
      continue;
    }
    if (notification.severity === "high") highUnreadCount += 1;
    if (notification.severity === "critical") criticalUnreadCount += 1;
    if (
      highestUnreadSeverity === null ||
      severityRank(notification.severity) > severityRank(highestUnreadSeverity)
    ) {
      highestUnreadSeverity = notification.severity;
    }
    const handle = normalizedHandle(notification.author_handle ?? "");
    if (handle) {
      accountUnreadCounts[handle] = (accountUnreadCounts[handle] ?? 0) + 1;
    }
  }
  const unreadCount = socketNotifications.filter((item) => !item.notification.read_at_ms).length;
  if (unreadCount === 0) {
    return null;
  }
  return {
    subscriber_key: "local",
    unread_count: unreadCount,
    high_unread_count: highUnreadCount,
    critical_unread_count: criticalUnreadCount,
    highest_unread_severity: highestUnreadSeverity,
    account_unread_counts: accountUnreadCounts,
  };
}

function severityRank(severity: string | null): number {
  if (severity === "critical") return 3;
  if (severity === "high") return 2;
  if (severity === "warning") return 1;
  return 0;
}
```

Then compute:

```ts
const socketSummary = summaryFromSocketNotifications(socketNotifications);
```

Return:

```ts
notificationSummary:
  summaryQuery.data?.data ?? notificationsQuery.data?.data.summary ?? socketSummary ?? fallbackSummary ?? null,
```

- [ ] **Step 7: Only invalidate notification queries when drawer is open**

Change the socket invalidation effect:

```ts
useEffect(() => {
  if (!latestSocketNotificationId || !drawerOpen) {
    return;
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
  void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
}, [drawerOpen, latestSocketNotificationId, queryClient]);
```

- [ ] **Step 8: Run notification tests**

Run:

```bash
cd web && npm test -- --run tests/routes/notifications.route.test.tsx
```

Expected: notification route tests pass.

- [ ] **Step 9: Commit notification on-demand change**

```bash
git add web/src/features/notifications/useNotificationsController.ts web/tests/routes/notifications.route.test.tsx
git commit -m "fix: make notification summary on demand"
```

## Task 4: Aggregate Notification Summary In PostgreSQL

**Files:**
- Modify: `src/gmgn_twitter_intel/domains/notifications/repositories/notification_repository.py`
- Modify: `tests/integration/test_notification_repository.py`
- Modify: `tests/integration/test_api_http.py`

- [ ] **Step 1: Add repository test for aggregate SQL shape**

In `tests/integration/test_notification_repository.py`, add this helper near the top:

```python
class RecordingConn:
    def __init__(self, conn):
        self.conn = conn
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        self.statements.append(str(sql))
        return self.conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.conn, name)
```

Add this test after `test_summary_and_mark_read_use_subscriber_read_state`:

```python
def test_summary_uses_sql_aggregates_without_materializing_unread_rows(tmp_path):
    repo = repository(tmp_path)
    for index in range(25):
        row = repo.insert_notification(
            dedup_key=f"activity:event-{index}",
            rule_id="watched_account_activity",
            severity="critical" if index == 0 else "high" if index % 5 == 0 else "info",
            title="activity",
            body="new post",
            entity_type="account",
            entity_key=f"account:handle{index % 3}",
            author_handle=f"handle{index % 3}",
            event_id=f"event-{index}",
            source_table="events",
            source_id=f"event-{index}",
            occurrence_at_ms=1_700_000_000_000 + index,
            payload={},
            channels=["in_app"],
        )
        assert row is not None
        if index % 4 == 0:
            repo.mark_read(
                notification_id=row["notification_id"],
                subscriber_key="local",
                read_at_ms=1_700_000_010_000 + index,
            )

    recording = RecordingConn(repo.conn)
    summary = NotificationRepository(recording).summary(subscriber_key="local")

    assert summary["unread_count"] == 18
    assert summary["critical_unread_count"] == 0
    assert summary["high_unread_count"] == 4
    assert summary["highest_unread_severity"] == "high"
    assert summary["account_unread_counts"] == {"handle0": 6, "handle1": 6, "handle2": 6}
    joined_sql = "\n".join(recording.statements)
    assert "COUNT(*)" in joined_sql
    assert "GROUP BY n.author_handle" in joined_sql
    assert "SELECT n.notification_id, n.severity, n.author_handle" not in joined_sql
```

- [ ] **Step 2: Run repository test and verify failure**

Run:

```bash
uv run pytest tests/integration/test_notification_repository.py::test_summary_uses_sql_aggregates_without_materializing_unread_rows -q
```

Expected before implementation: fails because `summary()` still selects `n.notification_id, n.severity, n.author_handle`.

- [ ] **Step 3: Replace Python row aggregation with SQL aggregates**

In `src/gmgn_twitter_intel/domains/notifications/repositories/notification_repository.py`, replace `summary()` with:

```python
    def summary(self, *, subscriber_key: str = "local", since_ms: int | None = None) -> dict[str, Any]:
        clauses = ["r.read_at_ms IS NULL"]
        params: list[Any] = [subscriber_key]
        if since_ms is not None:
            clauses.append("n.last_seen_at_ms >= %s")
            params.append(int(since_ms))
        where = " AND ".join(clauses)
        summary_row = self.conn.execute(
            f"""
            WITH unread AS (
              SELECT n.severity
              FROM notifications n
              LEFT JOIN notification_reads r
                ON r.notification_id = n.notification_id
               AND r.subscriber_key = %s
              WHERE {where}
            )
            SELECT
              COUNT(*) AS unread_count,
              COALESCE(SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END), 0) AS high_unread_count,
              COALESCE(SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END), 0) AS critical_unread_count,
              COALESCE(MAX(CASE severity
                WHEN 'critical' THEN 3
                WHEN 'high' THEN 2
                WHEN 'warning' THEN 1
                ELSE 0
              END), -1) AS highest_rank
            FROM unread
            """,
            params,
        ).fetchone()
        author_rows = self.conn.execute(
            f"""
            SELECT n.author_handle, COUNT(*) AS unread_count
            FROM notifications n
            LEFT JOIN notification_reads r
              ON r.notification_id = n.notification_id
             AND r.subscriber_key = %s
            WHERE {where}
              AND n.author_handle IS NOT NULL
            GROUP BY n.author_handle
            ORDER BY n.author_handle
            """,
            params,
        ).fetchall()
        highest_rank = int(summary_row["highest_rank"] if summary_row is not None else -1)
        highest = _severity_from_rank(highest_rank)
        return {
            "subscriber_key": subscriber_key,
            "unread_count": int(summary_row["unread_count"] if summary_row is not None else 0),
            "high_unread_count": int(summary_row["high_unread_count"] if summary_row is not None else 0),
            "critical_unread_count": int(
                summary_row["critical_unread_count"] if summary_row is not None else 0
            ),
            "highest_unread_severity": highest,
            "account_unread_counts": {
                str(row["author_handle"]): int(row["unread_count"]) for row in author_rows
            },
        }
```

Add helper near `_normalize_severity`:

```python
def _severity_from_rank(rank: int) -> str | None:
    if rank >= 3:
        return "critical"
    if rank == 2:
        return "high"
    if rank == 1:
        return "warning"
    if rank == 0:
        return "info"
    return None
```

- [ ] **Step 4: Run notification repository tests**

Run:

```bash
uv run pytest tests/integration/test_notification_repository.py -q
```

Expected: all notification repository tests pass.

- [ ] **Step 5: Run API notification contract tests**

Run:

```bash
uv run pytest tests/integration/test_api_http.py::test_api_exposes_notification_list_summary_and_read_state tests/integration/test_api_http.py::test_api_marks_author_notifications_read -q
```

Expected: both API tests pass.

- [ ] **Step 6: Commit backend aggregate fix**

```bash
git add src/gmgn_twitter_intel/domains/notifications/repositories/notification_repository.py tests/integration/test_notification_repository.py tests/integration/test_api_http.py
git commit -m "fix: aggregate notification summary in sql"
```

## Task 5: Architecture Gates And Full Verification

**Files:**
- Modify only if tests expose narrow issues in files already touched by Tasks 1-4.

- [ ] **Step 1: Run frontend lint and architecture tests**

Run:

```bash
cd web && npm run lint
```

Expected: ESLint and architecture tests pass. If CSS ownership fails, fix only owner-local imports/selectors caused by this change.

- [ ] **Step 2: Run frontend typecheck**

Run:

```bash
cd web && npm run typecheck
```

Expected: TypeScript passes with no `ShellRouteContext` stale property references.

- [ ] **Step 3: Run focused frontend route tests**

Run:

```bash
cd web && npm test -- --run tests/routes/live-radar.route.test.tsx tests/routes/notifications.route.test.tsx tests/component/features/cockpit/ui/CockpitTopbar.test.tsx
```

Expected: focused frontend tests pass.

- [ ] **Step 4: Run sidebar e2e across desktop**

Run:

```bash
cd web && npm run test:e2e -- --project=desktop-1366 tests/e2e/golden-paths/sidebar-navigation.spec.ts --reporter=line
```

Expected: normal, delayed API, and failed API desktop route-click tests pass.

- [ ] **Step 5: Run backend notification tests**

Run:

```bash
uv run pytest tests/integration/test_notification_repository.py tests/integration/test_api_http.py::test_api_exposes_notification_list_summary_and_read_state tests/integration/test_api_http.py::test_api_marks_author_notifications_read -q
```

Expected: backend notification tests pass.

- [ ] **Step 6: Run full gate**

Run:

```bash
make check-all
```

Expected: exits 0. Save the full output into the verification artifact required by `docs/WORKFLOW.md`.

- [ ] **Step 7: Create verification artifact**

Create `docs/superpowers/plans/active/2026-05-23-sidebar-navigation-latency-root-fix-verification-cn.md` with:

```markdown
# Sidebar Navigation Latency Root Fix Verification

## Coverage

- Shell navigation data dependency removed.
- Notification summary closed-drawer polling removed.
- Notification summary SQL aggregation implemented.
- Sidebar e2e covers normal, delayed API, and failed API route switching.

## Commands

<paste full command outputs here>

## Skipped Tests

- None, unless a command above records a skip.

## E2E Golden Path

- `desktop-1366` sidebar navigation spec passed.

## Remaining Risks

- None known after the listed commands pass.
```

- [ ] **Step 8: Commit verification**

```bash
git add docs/superpowers/plans/active/2026-05-23-sidebar-navigation-latency-root-fix-verification-cn.md
git commit -m "docs: verify sidebar navigation latency root fix"
```

