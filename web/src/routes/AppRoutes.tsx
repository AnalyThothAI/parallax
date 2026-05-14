import type { AppSession } from "@app/useAppSession";
import { CockpitShell, SearchShell, useCockpitStatusQuery } from "@features/cockpit";
import {
  buildLiveSignalTapeItems,
  useLiveRadarRouteData,
  useLiveRecentQuery,
  useLiveRouteState,
  useLiveSelection,
} from "@features/live";
import { useNotificationsController } from "@features/notifications";
import { useSignalLabCompactQuery } from "@features/signal-lab";
import { buildWatchlistAccountCases, buildWatchlistRows } from "@features/watchlist";
import type { LivePayload } from "@lib/types";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import type { MarketTargetRef } from "@shared/socket/socketTypes";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { LiveRadarRoute, LiveRoute } from "./live.route";
import { SearchRoute } from "./search.route";
import { SignalLabPulseRoute } from "./signal-lab.pulse.route";
import { SignalLabRoute } from "./signal-lab.route";
import { StocksRoute } from "./stocks.route";
import { TokenTargetRoute } from "./token-target.route";
import { WatchlistRoute } from "./watchlist.route";

const EMPTY_HANDLES: string[] = [];
const EMPTY_LIVE_ITEMS: LivePayload[] = [];

export function AppRoutes({ session }: { session: AppSession }) {
  const queryClient = useQueryClient();
  const liveRoute = useLiveRouteState();
  const statusQuery = useCockpitStatusQuery({ token: session.token });
  const recentQuery = useLiveRecentQuery({
    handles: liveRoute.handles,
    scope: liveRoute.scope,
    token: session.token,
  });
  const liveRadar = useLiveRadarRouteData({
    scope: liveRoute.scope,
    token: session.token,
    window: liveRoute.window,
  });
  const signalLabCompact = useSignalLabCompactQuery({ token: session.token });
  const socketSnapshot = useSocketSnapshot();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const bootstrapHandles = session.bootstrapHandles;
  const decisionCounts = liveRadar.decisionCounts;
  const handles = liveRoute.handles;
  const isAssetFlowLoading = liveRadar.isAssetFlowLoading;
  const isRecentLoading = recentQuery.isPending;
  const marketTargets = liveRadar.marketTargets;
  const recentReplayItems = recentQuery.data?.data.items ?? EMPTY_LIVE_ITEMS;
  const scope = liveRoute.scope;
  const signalLabOverviewData = signalLabCompact.overviewData;
  const signalLabPulseData = signalLabCompact.pulseData;
  const signalPulseColdLoading = signalLabCompact.signalPulseColdLoading;
  const status = statusQuery.data?.data ?? null;
  const statusError = statusQuery.isError;
  const statusHandles = statusQuery.data?.data.handles ?? EMPTY_HANDLES;
  const statusLoading = Boolean(session.token) && statusQuery.isPending;
  const assetFlowError = liveRadar.assetFlowError;
  const token = session.token;
  const tokenItems = liveRadar.tokenItems;
  const windowKey = liveRoute.window;
  const liveItems = useMemo(
    () => mergeLiveItems(recentReplayItems, socketSnapshot.eventItems),
    [recentReplayItems, socketSnapshot.eventItems],
  );
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems],
  );
  const selection = useLiveSelection({
    scope,
    windowKey,
  });
  const notificationsController = useNotificationsController({
    fallbackSummary: status?.notifications?.summary ?? null,
    setMobileTask: selection.setMobileTask,
    socketNotifications: socketSnapshot.notificationItems,
    token,
  });
  const watchlistRows = useMemo(
    () =>
      buildWatchlistRows({
        handles: statusHandles.length ? statusHandles : bootstrapHandles,
        accountUnreadCounts: notificationsController.notificationSummary?.account_unread_counts,
        liveItems,
      }),
    [
      bootstrapHandles,
      liveItems,
      notificationsController.notificationSummary?.account_unread_counts,
      statusHandles,
    ],
  );
  const watchlistAccountCases = useMemo(
    () => buildWatchlistAccountCases({ rows: watchlistRows, liveItems }),
    [liveItems, watchlistRows],
  );

  const handleHotkey = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement;
    const isTyping = target.tagName === "INPUT" || target.tagName === "TEXTAREA";
    if (event.key === "/" && !isTyping) {
      event.preventDefault();
      searchInputRef.current?.focus();
      return;
    }
    if (isTyping) {
      return;
    }
    if (event.key === "1") liveRoute.updateWindow("5m");
    if (event.key === "2") liveRoute.updateWindow("1h");
    if (event.key === "3") liveRoute.updateWindow("4h");
    if (event.key === "4") liveRoute.updateWindow("24h");
  };

  const topbarProps = {
    search: {
      inputRef: searchInputRef,
      onSubmitQuery: selection.submitEvidenceSearch,
    },
    status: {
      socketStatus: socketSnapshot.status,
      lastSocketMessageAt: socketSnapshot.lastMessageAt,
      status,
      statusLoading,
      statusError,
      configReady: Boolean(token),
    },
    stats: {
      tokenItemsCount: tokenItems.length,
      windowKey,
      signalLabSummaryTrade: signalLabOverviewData?.summary.trade_candidate ?? 0,
      signalLabSummaryToken: signalLabOverviewData?.summary.token_watch ?? 0,
      signalLabSummaryTheme: signalLabOverviewData?.summary.theme_watch ?? 0,
    },
    notifications: {
      summary: notificationsController.notificationSummary,
      drawerOpen: notificationsController.drawerOpen,
      onToggleDrawer: notificationsController.toggleDrawer,
    },
    onRefresh: () => void queryClient.invalidateQueries(),
  };
  const notificationProps = {
    notifications: notificationsController.notifications,
    notificationSummary: notificationsController.notificationSummary,
    notificationDrawerOpen: notificationsController.drawerOpen,
    notificationsLoading: notificationsController.notificationsLoading,
    onCloseNotificationDrawer: notificationsController.closeDrawer,
    onMarkAllRead: notificationsController.markAllRead,
    onMarkRead: notificationsController.markRead,
    onOpenNotification: notificationsController.openNotification,
    socketNotifications: socketSnapshot.notificationItems,
  };
  const sideRailProps = {
    tokenItemsCount: tokenItems.length,
    scope,
    onScopeChange: liveRoute.updateScope,
    handles,
    onHandlesChange: liveRoute.updateHandles,
    onWindowChange: liveRoute.updateWindow,
    decisionCounts,
    watchlistRows,
  };
  const mobileProps = {
    mobileTask: selection.mobileTask,
    onMobileTaskChange: selection.handleMobileTaskChange,
  };
  const cockpitShellElement = (
    <CockpitShell
      mobile={mobileProps}
      notifications={notificationProps}
      sideRail={sideRailProps}
      topbar={topbarProps}
      onHotkey={handleHotkey}
    />
  );
  const searchShellElement = (
    <SearchShell notifications={notificationProps} topbar={topbarProps} onHotkey={handleHotkey} />
  );

  const livePageElement = (children?: ReactNode) => (
    <LiveRoute
      liveSignalTapeItems={liveSignalTapeItems}
      isRecentLoading={isRecentLoading}
      socketStatus={socketSnapshot.status}
      selectedTapeEventId={selection.selectedTapeEventId}
      onTapeSelect={selection.handleTapeSelect}
      signalLabPulseData={signalLabPulseData ?? null}
      signalPulseLoading={signalPulseColdLoading}
      selectedPulseItemId={selection.selectedPulseItemId}
      onSelectPulse={selection.selectPulseItem}
    >
      {children}
    </LiveRoute>
  );

  const liveRadarElement = (
    <LiveRadarRoute
      tokenItems={tokenItems}
      isAssetFlowLoading={isAssetFlowLoading}
      assetFlowError={assetFlowError}
      selectedTokenKey={null}
      onOpenTokenSearch={selection.openTokenSearchPage}
      onSelectToken={selection.selectToken}
      scope={scope}
      windowKey={windowKey}
      onScopeChange={liveRoute.updateScope}
      onWindowChange={liveRoute.updateWindow}
    />
  );

  return (
    <Routes>
      <Route element={cockpitShellElement}>
        <Route path="token/:targetType/:targetId" element={<TokenTargetRoute />} />
        <Route
          path="stocks"
          element={
            <StocksRoute
              token={token ?? ""}
              windowKey={windowKey}
              scope={scope}
              onScopeChange={liveRoute.updateScope}
              onWindowChange={liveRoute.updateWindow}
            />
          }
        />
        <Route path="watchlist" element={<WatchlistRoute accountCases={watchlistAccountCases} />} />
        <Route path="signal-lab/pulse/:candidateId" element={<SignalLabPulseRoute />} />
        <Route
          path="signal-lab"
          element={
            <SignalLabRoute
              selectedAccountEventId={selection.selectedAccountEventId}
              overviewData={signalLabOverviewData}
              onSelectAccountEvent={selection.selectAccountEvent}
            />
          }
        />
        <Route
          index
          element={livePageElement(
            <LiveMarketSubscription targets={marketTargets}>{liveRadarElement}</LiveMarketSubscription>,
          )}
        />
      </Route>
      <Route element={searchShellElement}>
        <Route path="search" element={<SearchRoute />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function LiveMarketSubscription({
  children,
  targets,
}: {
  children: ReactNode;
  targets: MarketTargetRef[];
}) {
  useMarketSubscription(targets);
  return <>{children}</>;
}

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
