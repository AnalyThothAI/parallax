import { CockpitShell, SearchShell } from "@features/cockpit";
import {
  buildLiveSignalTapeItems,
  EvidenceDetailDrawer,
  LivePage,
  LiveRadar,
  TokenDetailDrawer,
  useLiveData,
  useLiveRouteState,
  useLiveSelection,
  type EvidenceDetailDrawerProps,
  type SelectedSignal,
} from "@features/live";
import { useNotificationsController } from "@features/notifications";
import { SearchIntelPage } from "@features/search";
import { PulseDetailPage, SignalLabInspector, SignalLabPage } from "@features/signal-lab";
import { StocksRadarPage } from "@features/stocks";
import { TokenTargetPage, useTokenDetailData } from "@features/token-target";
import type { LivePayload } from "@lib/types";
import { buildWatchlistRows } from "@lib/watchlist";
import { IntelSocketProvider } from "@shared/socket/IntelSocketProvider";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import type { MarketTargetRef } from "@shared/socket/socketTypes";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

type LiveData = ReturnType<typeof useLiveData>;
type LiveRouteState = ReturnType<typeof useLiveRouteState>;

export function CockpitApp() {
  const liveRoute = useLiveRouteState();
  const liveData = useLiveData({
    handles: liveRoute.handles,
    radarSortMode: liveRoute.sort,
    scope: liveRoute.scope,
    windowKey: liveRoute.window,
  });

  return (
    <IntelSocketProvider
      token={liveData.token}
      handles={liveData.handles}
      replay={liveData.replayLimit}
      notifications
    >
      <CockpitAppRoutes liveData={liveData} liveRoute={liveRoute} />
    </IntelSocketProvider>
  );
}

function CockpitAppRoutes({
  liveData,
  liveRoute,
}: {
  liveData: LiveData;
  liveRoute: LiveRouteState;
}) {
  const queryClient = useQueryClient();
  const socketSnapshot = useSocketSnapshot();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const {
    bootstrapHandles,
    compactSignalPulseItems,
    decisionCounts,
    handles,
    isAssetFlowLoading,
    isRecentLoading,
    marketTargets,
    radarSortMode,
    recentReplayItems,
    scope,
    signalLabOverviewData,
    signalLabPulseData,
    signalLabPulseTotal,
    signalPulseColdLoading,
    signalPulseFetching,
    status,
    statusError,
    statusHandles,
    statusLoading,
    assetFlowError,
    token,
    tokenItems,
    windowKey,
  } = liveData;
  const liveItems = useMemo(
    () => mergeLiveItems(recentReplayItems, socketSnapshot.eventItems),
    [recentReplayItems, socketSnapshot.eventItems],
  );
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems],
  );
  const selection = useLiveSelection({
    compactSignalPulseItems,
    scope,
    signalPulseFetching,
    tokenItems,
    windowKey,
  });
  const tokenDetail = useTokenDetailData({
    detailWindow: selection.detailWindow,
    postRange: selection.postRange,
    postSortMode: selection.postSortMode,
    scope,
    target: selection.drawerTargetRef,
    token,
  });
  const selectedEvidenceDetails = useMemo(
    () => resolveEvidenceDetails(selection.selectedSignal),
    [selection.selectedSignal],
  );
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

  const detailPanel = selection.selectedPulseItem ? (
    <SignalLabInspector item={selection.selectedPulseItem} />
  ) : selectedEvidenceDetails ? (
    <EvidenceDetailDrawer {...selectedEvidenceDetails} />
  ) : (
    <TokenDetailDrawer
      accountQuality={tokenDetail.accountQuality}
      activeTab={selection.detailTab}
      detailMode={selection.detailMode}
      detailWindow={selection.detailWindow}
      hideDuplicateClusters={selection.hideDuplicateClusters}
      isAccountQualityLoading={tokenDetail.isAccountQualityLoading}
      signalLabLoading={signalPulseFetching}
      isPostsFetchingNextPage={tokenDetail.isPostsFetchingNextPage}
      isPostsLoading={tokenDetail.isPostsLoading}
      isTimelineLoading={tokenDetail.isTimelineLoading}
      postRange={selection.postRange}
      postSortMode={selection.postSortMode}
      posts={tokenDetail.posts}
      selectedBucketStartMs={selection.selectedBucketStartMs}
      selectedEventId={selection.selectedEventId}
      timeline={tokenDetail.timeline}
      token={selection.selectedToken}
      watchedPostsOnly={selection.watchedPostsOnly}
      onHideDuplicateClustersChange={selection.setHideDuplicateClusters}
      onBackToTimeline={selection.handleTimelineBack}
      onDetailWindowChange={selection.handleDetailWindowChange}
      onLoadMorePosts={tokenDetail.loadMorePosts}
      onOpenSearchIntel={selection.openTokenSearchPage}
      onPostRangeChange={selection.setPostRange}
      onPostSortModeChange={selection.setPostSortMode}
      onSelectedEventChange={selection.setSelectedEventId}
      onTabChange={selection.handleDetailTabChange}
      onTimelineBucketSelect={selection.handleTimelineBucketSelect}
      onWatchedPostsOnlyChange={selection.setWatchedPostsOnly}
    />
  );

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
    signalLabPulseTotal,
    scope,
    onScopeChange: liveRoute.updateScope,
    handles,
    onHandlesChange: liveRoute.updateHandles,
    onWindowChange: liveRoute.updateWindow,
    decisionCounts,
    watchlistRows,
    onMobileTaskChange: selection.handleMobileTaskChange,
  };
  const mobileProps = {
    mobileTask: selection.mobileTask,
    detailAvailable: selection.detailAvailable,
    onMobileTaskChange: selection.handleMobileTaskChange,
  };
  const cockpitShellElement = (
    <CockpitShell
      detailPanel={detailPanel}
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

  const livePageElement = (
    <LivePage
      liveSignalTapeItems={liveSignalTapeItems}
      isRecentLoading={isRecentLoading}
      socketStatus={socketSnapshot.status}
      selectedTapeEventId={selection.selectedTapeEventId}
      onTapeSelect={selection.handleTapeSelect}
      signalLabPulseData={signalLabPulseData ?? null}
      signalPulseLoading={signalPulseColdLoading}
      selectedPulseItemId={selection.selectedPulseItemId}
      onOpenLab={selection.onOpenLab}
      onSelectPulse={selection.selectPulseItem}
    />
  );

  const liveRadarElement = (
    <LiveRadar
      tokenItems={tokenItems}
      isAssetFlowLoading={isAssetFlowLoading}
      assetFlowError={assetFlowError}
      selectedTokenKey={selection.selectedTokenKey}
      radarSortMode={radarSortMode}
      onOpenTokenSearch={selection.openTokenSearchPage}
      onSelectToken={selection.selectToken}
      onSortModeChange={liveRoute.updateSort}
      scope={scope}
      windowKey={windowKey}
      onScopeChange={liveRoute.updateScope}
      onWindowChange={liveRoute.updateWindow}
    />
  );

  return (
    <Routes>
      <Route element={cockpitShellElement}>
        <Route element={livePageElement}>
          <Route
            index
            element={
              <LiveMarketSubscription targets={marketTargets}>
                {liveRadarElement}
              </LiveMarketSubscription>
            }
          />
          <Route path="token/:targetType/:targetId" element={<TokenTargetPage />} />
        </Route>
        <Route
          path="stocks"
          element={
            <StocksRadarPage
              token={token ?? ""}
              windowKey={windowKey}
              scope={scope}
              onScopeChange={liveRoute.updateScope}
              onWindowChange={liveRoute.updateWindow}
            />
          }
        />
        <Route
          path="signal-lab"
          element={
            <SignalLabPage
              selectedAccountEventId={selection.selectedAccountEventId}
              overviewData={signalLabOverviewData}
              onSelectAccountEvent={selection.selectAccountEvent}
            />
          }
        >
          <Route path="pulse/:candidateId" element={<PulseDetailPage />} />
        </Route>
      </Route>
      <Route element={searchShellElement}>
        <Route path="search" element={<SearchIntelPage />} />
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

function resolveEvidenceDetails(signal: SelectedSignal): EvidenceDetailDrawerProps | null {
  if (!signal) {
    return null;
  }
  if (signal.kind === "event") {
    return {
      mode: "event",
      event: signal.item.event,
      entities: signal.item.entities,
      alerts: signal.item.alerts,
      tokenIntents: signal.item.token_intents ?? [],
      tokenResolutions: signal.item.token_resolutions ?? [],
      sourceLabel: "live",
    };
  }
  return null;
}
