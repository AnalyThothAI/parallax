import { useMemo, useRef } from "react";
import type { KeyboardEvent } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { SearchData } from "../api/types";
import { CockpitLayout } from "../components/CockpitLayout";
import { EvidenceDetailDrawer, type EvidenceDetailDrawerProps } from "../components/EvidenceDetailDrawer";
import { LivePage } from "../components/LivePage";
import { LiveRadar } from "../components/LiveRadar";
import { PulseDetailPage } from "../components/PulseDetailPage";
import { SignalLabInspector } from "../components/SignalLabInspector";
import { SignalLabPage } from "../components/SignalLabPage";
import { TokenDetailDrawer } from "../components/TokenDetailDrawer";
import { TokenTargetPage } from "../components/TokenTargetPage";
import { useLiveData } from "../features/live/useLiveData";
import { useLiveSelection, type SelectedSignal } from "../features/live/useLiveSelection";
import { useNotificationsController } from "../features/notifications/useNotificationsController";
import { useTokenDetailData } from "../features/token-target/useTokenDetailData";
import { buildWatchlistRows } from "../lib/watchlist";
import { useTraderStore } from "../store/useTraderStore";

export function CockpitApp() {
  const queryClient = useQueryClient();

  const search = useTraderStore((state) => state.search);
  const setWindow = useTraderStore((state) => state.setWindow);
  const setScope = useTraderStore((state) => state.setScope);
  const setHandles = useTraderStore((state) => state.setHandles);
  const setSearch = useTraderStore((state) => state.setSearch);
  const setRadarSortMode = useTraderStore((state) => state.setRadarSortMode);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const liveData = useLiveData();
  const {
    bootstrapHandles,
    compactSignalPulseItems,
    currentSearchData,
    decisionCounts,
    handles,
    isAssetFlowLoading,
    isRecentLoading,
    isSignalLabPulseColdLoading,
    isSignalLabPulseFetching,
    liveItems,
    liveSignalTapeItems,
    radarSortMode,
    scope,
    searchError,
    searchFetching,
    signalLabOverviewData,
    signalLabPulseData,
    signalLabPulseTotal,
    socket,
    status,
    statusError,
    statusHandles,
    statusLoading,
    assetFlowError,
    token,
    tokenItems,
    windowKey
  } = liveData;
  const selection = useLiveSelection({
    compactSignalPulseItems,
    isSignalLabPulseFetching,
    scope,
    tokenItems,
    windowKey
  });
  const tokenDetail = useTokenDetailData({
    detailWindow: selection.detailWindow,
    postRange: selection.postRange,
    postSortMode: selection.postSortMode,
    scope,
    target: selection.drawerTargetRef,
    token
  });
  const selectedEvidenceDetails = useMemo(
    () =>
      resolveEvidenceDetails(selection.selectedSignal, {
        currentSearchData,
        searchError,
        searchFetching
      }),
    [currentSearchData, searchError, searchFetching, selection.selectedSignal]
  );
  const notificationsController = useNotificationsController({
    fallbackSummary: status?.notifications?.summary ?? null,
    setMobileTask: selection.setMobileTask,
    socketNotifications: socket.notifications,
    token
  });
  const watchlistRows = useMemo(
    () =>
      buildWatchlistRows({
        handles: statusHandles.length ? statusHandles : bootstrapHandles,
        accountUnreadCounts: notificationsController.notificationSummary?.account_unread_counts,
        liveItems
      }),
    [
      bootstrapHandles,
      liveItems,
      notificationsController.notificationSummary?.account_unread_counts,
      statusHandles
    ]
  );

  const handleHotkey = (event: KeyboardEvent<HTMLElement>) => {
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
    if (event.key === "1") setWindow("5m");
    if (event.key === "2") setWindow("1h");
    if (event.key === "3") setWindow("4h");
    if (event.key === "4") setWindow("24h");
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
      isSignalLabLoading={isSignalLabPulseFetching}
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
      onPostRangeChange={selection.setPostRange}
      onPostSortModeChange={selection.setPostSortMode}
      onSelectedEventChange={selection.setSelectedEventId}
      onTabChange={selection.handleDetailTabChange}
      onTimelineBucketSelect={selection.handleTimelineBucketSelect}
      onWatchedPostsOnlyChange={selection.setWatchedPostsOnly}
    />
  );

  const layoutElement = (
    <CockpitLayout
      searchInputRef={searchInputRef}
      searchValue={search}
      onSearchChange={setSearch}
      onSubmitSearch={selection.submitEvidenceSearch}
      socketStatus={socket.status}
      lastSocketMessageAt={socket.lastMessageAt}
      status={status}
      statusLoading={statusLoading}
      statusError={statusError}
      configReady={Boolean(token)}
      liveItemsCount={liveItems.length}
      tokenItemsCount={tokenItems.length}
      windowKey={windowKey}
      signalLabSummaryTrade={signalLabOverviewData?.summary.trade_candidate ?? 0}
      signalLabSummaryToken={signalLabOverviewData?.summary.token_watch ?? 0}
      signalLabSummaryTheme={signalLabOverviewData?.summary.theme_watch ?? 0}
      signalLabPulseTotal={signalLabPulseTotal}
      notifications={notificationsController.notifications}
      notificationSummary={notificationsController.notificationSummary}
      notificationDrawerOpen={notificationsController.drawerOpen}
      onToggleNotificationDrawer={notificationsController.toggleDrawer}
      onCloseNotificationDrawer={notificationsController.closeDrawer}
      notificationsLoading={notificationsController.notificationsLoading}
      onMarkAllRead={notificationsController.markAllRead}
      onMarkRead={notificationsController.markRead}
      onOpenNotification={notificationsController.openNotification}
      socketNotifications={socket.notifications}
      onRefresh={() => void queryClient.invalidateQueries()}
      scope={scope}
      onScopeChange={setScope}
      handles={handles}
      onHandlesChange={setHandles}
      onWindowChange={setWindow}
      decisionCounts={decisionCounts}
      watchlistRows={watchlistRows}
      mobileTask={selection.mobileTask}
      detailAvailable={selection.detailAvailable}
      onMobileTaskChange={selection.handleMobileTaskChange}
      detailPanel={detailPanel}
      onHotkey={handleHotkey}
    />
  );

  const livePageElement = (
    <LivePage
      liveSignalTapeItems={liveSignalTapeItems}
      isRecentLoading={isRecentLoading}
      socketStatus={socket.status}
      selectedTapeEventId={selection.selectedTapeEventId}
      onTapeSelect={selection.handleTapeSelect}
      signalLabPulseData={signalLabPulseData ?? null}
      isSignalLabPulseLoading={isSignalLabPulseColdLoading}
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
      onSelectToken={selection.selectToken}
      onOpenToken={selection.openTokenPage}
      onSortModeChange={setRadarSortMode}
      scope={scope}
      windowKey={windowKey}
      onScopeChange={setScope}
      onWindowChange={setWindow}
    />
  );

  return (
    <Routes>
      <Route element={layoutElement}>
        <Route element={livePageElement}>
          <Route index element={liveRadarElement} />
          <Route path="token/:targetType/:targetId" element={<TokenTargetPage />} />
        </Route>
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function resolveEvidenceDetails(
  signal: SelectedSignal,
  data: {
    currentSearchData: SearchData | null;
    searchError: Error | null;
    searchFetching: boolean;
  }
): EvidenceDetailDrawerProps | null {
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
      sourceLabel: "live"
    };
  }
  if (signal.kind === "query") {
    return {
      mode: "query",
      query: signal.query,
      data: data.currentSearchData,
      isFetching: data.searchFetching,
      error: data.searchError
    };
  }
  return null;
}
