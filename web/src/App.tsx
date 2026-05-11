import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { getApi, getBootstrap } from "./api/client";
import { getNotifications, getNotificationSummary, markAllNotificationsRead, markNotificationRead } from "./api/notifications";
import { mergeTokenPostPages, useTokenTargetPosts, useTokenTargetTimeline } from "./api/useTokenTargetQueries";
import type {
  AccountQualityData,
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  LivePayload,
  MarketUpdatePayload,
  NotificationItem,
  RecentData,
  SearchData,
  SignalPulseData,
  SignalPulseItem,
  StatusData,
  TokenFlowItem
} from "./api/types";
import { useIntelSocket } from "./api/useIntelSocket";
import { CockpitLayout } from "./components/CockpitLayout";
import { EvidenceDetailDrawer, type EvidenceDetailDrawerProps } from "./components/EvidenceDetailDrawer";
import { LivePage } from "./components/LivePage";
import { LiveRadar } from "./components/LiveRadar";
import { type LiveSignalTapeItem, tokenTapeReason } from "./components/LiveSignalTape";
import type { MobileTask } from "./components/MobileTaskNav";
import { PulseDetailPage } from "./components/PulseDetailPage";
import { SignalLabInspector } from "./components/SignalLabInspector";
import { SignalLabPage } from "./components/SignalLabPage";
import { TokenDetailDrawer } from "./components/TokenDetailDrawer";
import { TokenTargetPage } from "./components/TokenTargetPage";
import {
  compactNumber,
  eventText,
  formatRelativeTime,
  tokenKey
} from "./lib/format";
import { tokenForSearchQuery } from "./lib/searchIntent";
import { countDecisions, sortTokenItems, tokenRadarItems } from "./lib/tokenRadar";
import { buildWatchlistRows } from "./lib/watchlist";
import { targetRefFromTokenItem } from "./domain/tokenTarget";
import { useTraderStore } from "./store/useTraderStore";

type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "pulse"; item: SignalPulseItem }
  | { kind: "query"; query: string }
  | null;

const SIGNAL_LAB_COMPACT_WINDOW = "1h";
const SIGNAL_LAB_COMPACT_SCOPE = "all";

export function App() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const isSignalLabRoute = location.pathname.startsWith("/signal-lab");

  const windowKey = useTraderStore((state) => state.window);
  const scope = useTraderStore((state) => state.scope);
  const handles = useTraderStore((state) => state.handles);
  const search = useTraderStore((state) => state.search);
  const submittedSearch = useTraderStore((state) => state.submittedSearch);
  const token = useTraderStore((state) => state.token);
  const radarSortMode = useTraderStore((state) => state.radarSortMode);
  const detailTab = useTraderStore((state) => state.detailTab);
  const detailWindow = useTraderStore((state) => state.detailWindow);
  const detailMode = useTraderStore((state) => state.detailMode);
  const selectedBucketStartMs = useTraderStore((state) => state.selectedBucketStartMs);
  const selectedEventId = useTraderStore((state) => state.selectedEventId);
  const postRange = useTraderStore((state) => state.postRange);
  const postSortMode = useTraderStore((state) => state.postSortMode);
  const hideDuplicateClusters = useTraderStore((state) => state.hideDuplicateClusters);
  const watchedPostsOnly = useTraderStore((state) => state.watchedPostsOnly);
  const setToken = useTraderStore((state) => state.setToken);
  const setWindow = useTraderStore((state) => state.setWindow);
  const setScope = useTraderStore((state) => state.setScope);
  const setHandles = useTraderStore((state) => state.setHandles);
  const setSearch = useTraderStore((state) => state.setSearch);
  const submitSearch = useTraderStore((state) => state.submitSearch);
  const runSearch = useTraderStore((state) => state.runSearch);
  const setRadarSortMode = useTraderStore((state) => state.setRadarSortMode);
  const setDetailTab = useTraderStore((state) => state.setDetailTab);
  const setDetailWindow = useTraderStore((state) => state.setDetailWindow);
  const setDetailMode = useTraderStore((state) => state.setDetailMode);
  const setSelectedBucketStartMs = useTraderStore((state) => state.setSelectedBucketStartMs);
  const setSelectedEventId = useTraderStore((state) => state.setSelectedEventId);
  const setPostRange = useTraderStore((state) => state.setPostRange);
  const setPostSortMode = useTraderStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useTraderStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useTraderStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const [mobileTask, setMobileTask] = useState<MobileTask>("radar");
  const [notificationDrawerOpen, setNotificationDrawerOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: getBootstrap,
    staleTime: Infinity
  });

  useEffect(() => {
    if (bootstrapQuery.data?.data.ws_token) {
      setToken(bootstrapQuery.data.data.ws_token);
    }
  }, [bootstrapQuery.data?.data.ws_token, setToken]);

  const replayLimit = Math.min(25, bootstrapQuery.data?.data.replay_limit ?? 25);

  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: () => getApi<StatusData>("/api/status", { token }),
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const recentQuery = useQuery({
    queryKey: ["recent", scope, handles],
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: { limit: 80, scope, handles }
      }),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const assetFlowQuery = useQuery({
    queryKey: ["token-radar", windowKey, scope],
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window: windowKey, limit: 48, scope }
      }),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const signalPulseOverviewQuery = useQuery({
    queryKey: ["signal-lab-overview", SIGNAL_LAB_COMPACT_WINDOW, SIGNAL_LAB_COMPACT_SCOPE],
    queryFn: () =>
      getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: SIGNAL_LAB_COMPACT_WINDOW,
          scope: SIGNAL_LAB_COMPACT_SCOPE,
          limit: 1
        }
      }),
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const signalLabPulseQuery = useQuery({
    queryKey: ["signal-lab-pulse-compact", SIGNAL_LAB_COMPACT_SCOPE, SIGNAL_LAB_COMPACT_WINDOW],
    queryFn: () =>
      getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: SIGNAL_LAB_COMPACT_WINDOW,
          scope: SIGNAL_LAB_COMPACT_SCOPE,
          limit: 80,
          sort: "recent"
        }
      }),
    enabled: Boolean(token),
    refetchInterval: 20_000
  });

  const searchQuery = useQuery({
    queryKey: ["search", submittedSearch],
    queryFn: () =>
      getApi<SearchData>("/api/search", {
        token,
        params: { q: submittedSearch, limit: 36, scope: "all" }
      }),
    enabled: Boolean(token && submittedSearch)
  });

  const rawTokenItems = useMemo(
    () => tokenRadarItems(assetFlowQuery.data?.data, windowKey, scope),
    [assetFlowQuery.data?.data, scope, windowKey]
  );
  const tokenItems = useMemo(() => sortTokenItems(rawTokenItems, radarSortMode), [rawTokenItems, radarSortMode]);
  const marketTargets = useMemo(
    () => rawTokenItems.flatMap((item) => {
      const target = targetRefFromTokenItem(item);
      return target ? [target] : [];
    }),
    [rawTokenItems]
  );
  const socket = useIntelSocket({ token, handles, replay: replayLimit, notifications: true, marketTargets });
  const selectedToken = selectedSignal?.kind === "token" ? latestTokenForSelection(selectedSignal, tokenItems) : null;
  const selectedTokenKey = selectedToken ? tokenKey(selectedToken) : null;
  const drawerTargetRef = targetRefFromTokenItem(selectedToken);
  const tokenPostRequestSort = postSortMode === "catalyst" ? "catalyst" : "recent";

  const tokenTimelineQuery = useTokenTargetTimeline({ token, target: drawerTargetRef, window: detailWindow, scope });
  const tokenPostsQuery = useTokenTargetPosts({
    token,
    target: drawerTargetRef,
    window: detailWindow,
    scope,
    range: postRange,
    sort: tokenPostRequestSort,
  });

  const accountQualityHandles = useMemo(
    () => (tokenTimelineQuery.data?.data.authors ?? []).map((author) => author.handle).filter(Boolean).join(","),
    [tokenTimelineQuery.data?.data.authors]
  );
  const accountQualityQuery = useQuery({
    queryKey: ["account-quality", accountQualityHandles],
    queryFn: () =>
      getApi<AccountQualityData>("/api/account-quality", {
        token,
        params: { handles: accountQualityHandles }
      }),
    enabled: Boolean(token && accountQualityHandles)
  });

  const notificationSummaryQuery = useQuery({
    queryKey: ["notification-summary"],
    queryFn: () => getNotificationSummary(token),
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getNotifications(token),
    enabled: Boolean(token),
    refetchInterval: notificationDrawerOpen ? 8_000 : 20_000
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(token, notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });

  const liveItems = useMemo(() => {
    const replayItems = recentQuery.data?.data.items ?? [];
    const byId = new Map<string, LivePayload>();
    for (const item of [...replayItems, ...socket.events]) {
      byId.set(item.event.event_id, item);
    }
    return [...byId.values()].sort((a, b) => Number(b.event.received_at_ms ?? 0) - Number(a.event.received_at_ms ?? 0));
  }, [recentQuery.data?.data.items, socket.events]);

  const searchData = searchQuery.data?.data;
  const currentSearchData = searchData && String(searchData.query?.text ?? "") === submittedSearch ? searchData : null;
  const signalLabOverviewData = signalPulseOverviewQuery.data?.data ?? signalLabPulseQuery.data?.data;
  const signalLabPulseData = signalLabPulseQuery.data?.data ?? signalLabOverviewData;
  const signalLabPulseTotal = signalPulseTotal(signalLabOverviewData?.summary);
  const compactSignalPulseItems = signalLabPulseData?.items ?? [];
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems]
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const tokenPostsData = useMemo(() => mergeTokenPostPages(tokenPostsQuery.data?.pages), [tokenPostsQuery.data?.pages]);
  const selectedPulseItemId = selectedPulseItemIdForSelection(selectedSignal);
  const selectedPulseItem = selectedSignal?.kind === "pulse" ? latestPulseForSelection(selectedSignal.item, compactSignalPulseItems) : null;
  const selectedAccountEventId = selectedSignal?.kind === "event" ? selectedSignal.item.event.event_id : null;
  const selectedEvidenceDetails = useMemo(
    () =>
      resolveEvidenceDetails(selectedSignal, {
        currentSearchData,
        searchError: searchQuery.error instanceof Error ? searchQuery.error : null,
        searchFetching: searchQuery.isFetching
      }),
    [currentSearchData, searchQuery.error, searchQuery.isFetching, selectedSignal]
  );
  const notificationSummary = notificationSummaryQuery.data?.data ?? statusQuery.data?.data.notifications?.summary ?? null;
  const notifications = notificationsQuery.data?.data.items ?? [];
  const latestSocketNotificationId = socket.notifications[0]?.notification.notification_id ?? null;
  const socketMarketUpdates = socket.marketUpdates ?? [];
  const watchlistRows = useMemo(
    () =>
      buildWatchlistRows({
        handles: statusQuery.data?.data.handles ?? bootstrapQuery.data?.data.handles ?? [],
        accountUnreadCounts: notificationSummary?.account_unread_counts,
        liveItems
      }),
    [bootstrapQuery.data?.data.handles, liveItems, notificationSummary?.account_unread_counts, statusQuery.data?.data.handles]
  );

  useEffect(() => {
    if (!latestSocketNotificationId) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }, [latestSocketNotificationId, queryClient]);

  useEffect(() => {
    if (!socketMarketUpdates.length) {
      return;
    }
    patchTokenRadarMarketUpdate(queryClient, socketMarketUpdates[0]);
  }, [assetFlowQuery.dataUpdatedAt, queryClient, socketMarketUpdates]);

  useEffect(() => {
    if (!selectedSignal && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      setDetailTab("timeline");
      setDetailWindow(windowKey);
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
      setPostRange("current_window");
    }
  }, [selectedSignal, setDetailMode, setDetailTab, setDetailWindow, setPostRange, setSelectedBucketStartMs, setSelectedEventId, tokenItems, windowKey]);

  useEffect(() => {
    if (selectedSignal?.kind !== "token") {
      return;
    }
    const latest = tokenItems.find((item) => tokenKey(item) === selectedSignal.key);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "token", key: selectedSignal.key, item: latest });
      return;
    }
    if (!latest && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      setDetailTab("timeline");
      setDetailWindow(windowKey);
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
      setPostRange("current_window");
      return;
    }
    if (!latest) {
      setSelectedSignal(null);
    }
  }, [selectedSignal, setDetailMode, setDetailTab, setDetailWindow, setPostRange, setSelectedBucketStartMs, setSelectedEventId, tokenItems, windowKey]);

  useEffect(() => {
    if (selectedSignal?.kind !== "pulse") {
      return;
    }
    const latest = compactSignalPulseItems.find((item) => item.candidate_id === selectedSignal.item.candidate_id);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "pulse", item: latest });
      return;
    }
    if (!latest && !signalLabPulseQuery.isFetching) {
      setSelectedSignal(null);
    }
  }, [compactSignalPulseItems, selectedSignal, signalLabPulseQuery.isFetching]);

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailTab("timeline");
    setDetailWindow(windowKey);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setPostRange("current_window");
    setSelectedTapeEventId(tapeId);
    setMobileTask("detail");
  };

  const openTokenPage = (item: TokenFlowItem) => {
    const target = targetRefFromTokenItem(item);
    if (!target || !target.target_type || !target.target_id) {
      return;
    }
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailWindow(windowKey);
    setMobileTask("radar");
    navigate(`/token/${target.target_type}/${encodeURIComponent(target.target_id)}?window=${windowKey}&scope=${scope}`);
  };

  const selectPulseItem = (item: SignalPulseItem, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "pulse", item });
    setSelectedTapeEventId(item.candidate_id);
    setMobileTask("detail");
    if (options.openLab) {
      navigate("/signal-lab");
      setMobileTask("lab");
    }
  };

  const selectAccountEvent = (item: LivePayload) => {
    setSelectedSignal({ kind: "event", item });
    setSelectedTapeEventId(item.event.event_id);
    setMobileTask("detail");
  };

  const submitEvidenceSearch = () => {
    const query = search.trim();
    const tokenMatch = tokenForSearchQuery(query, tokenItems);
    if (tokenMatch) {
      selectToken(tokenMatch);
      return;
    }
    if (isSignalLabRoute) {
      const next = new URLSearchParams(location.search);
      if (query) {
        next.set("q", query);
      } else {
        next.delete("q");
      }
      const queryString = next.toString();
      navigate("/signal-lab" + (queryString ? "?" + queryString : ""));
      setSelectedSignal(null);
      setSelectedTapeEventId(null);
      setMobileTask("lab");
      return;
    }
    submitSearch();
    setSelectedSignal(query ? { kind: "query", query } : null);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
    setSelectedTapeEventId(null);
    setMobileTask(query ? "detail" : "radar");
  };

  const handleTapeSelect = (item: LiveSignalTapeItem) => {
    const id = tapeItemId(item);
    setSelectedTapeEventId(id);
    if (item.kind === "token") {
      selectToken(item.token, id);
      return;
    }
    setSelectedSignal({ kind: "event", item: item.payload });
    setMobileTask("detail");
  };

  const handleMobileTaskChange = (task: MobileTask) => {
    setMobileTask(task);
    if (task === "radar" || task === "tape") {
      navigate("/");
    }
  };

  const handleDetailTabChange = (tab: typeof detailTab) => {
    onTimelineExit(tab);
    setDetailTab(tab);
  };

  const handleDetailWindowChange = (window: typeof detailWindow) => {
    setDetailWindow(window);
    setDetailMode("compact");
    setSelectedBucketStartMs(null);
    setSelectedEventId(null);
  };

  const handleTimelineBucketSelect = (bucketStartMs: number) => {
    setDetailTab("timeline");
    setSelectedBucketStartMs(bucketStartMs);
    setSelectedEventId(null);
    setDetailMode("replay");
  };

  const handleTimelineBack = () => {
    setDetailMode("compact");
    setSelectedEventId(null);
  };

  const onTimelineExit = (tab: typeof detailTab) => {
    if (tab !== "timeline") {
      setDetailMode("compact");
      setSelectedBucketStartMs(null);
      setSelectedEventId(null);
    }
  };

  const openNotification = (notification: NotificationItem) => {
    markReadMutation.mutate(notification.notification_id);
    setNotificationDrawerOpen(false);
    if (notification.entity_type === "pulse_candidate" || notification.source_table === "pulse_candidates") {
      let q: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (typeof notification.payload?.candidate_id === "string") {
        q = notification.payload.candidate_id;
      } else if (notification.source_id) {
        q = notification.source_id;
      }
      navigate(buildSignalLabUrl({ q }));
      setMobileTask("lab");
      return;
    }
    if (notification.entity_type === "social_event" || notification.source_table === "social_event_extractions") {
      let q: string | null = null;
      let handle: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (notification.author_handle) {
        handle = normalizedHandle(notification.author_handle);
      } else if (notification.event_id) {
        q = notification.event_id;
      }
      navigate(buildSignalLabUrl({ q, handle }));
      setMobileTask("lab");
      return;
    }
    if (notification.symbol) {
      runSearch(`$${notification.symbol}`);
      navigate("/");
      setMobileTask("detail");
      return;
    }
    if (notification.author_handle) {
      runSearch(`@${notification.author_handle}`);
      navigate("/");
      setMobileTask("detail");
      return;
    }
    if (notification.event_id) {
      runSearch(notification.event_id);
      navigate("/");
      setMobileTask("detail");
    }
  };

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

  const onOpenLab = () => {
    navigate("/signal-lab");
    setMobileTask("lab");
  };

  const detailPanel = selectedPulseItem ? (
    <SignalLabInspector item={selectedPulseItem} />
  ) : selectedEvidenceDetails ? (
    <EvidenceDetailDrawer {...selectedEvidenceDetails} />
  ) : (
    <TokenDetailDrawer
      accountQuality={accountQualityQuery.data?.data}
      activeTab={detailTab}
      detailMode={detailMode}
      detailWindow={detailWindow}
      hideDuplicateClusters={hideDuplicateClusters}
      isAccountQualityLoading={accountQualityQuery.isFetching}
      isSignalLabLoading={signalLabPulseQuery.isFetching}
      isPostsFetchingNextPage={tokenPostsQuery.isFetchingNextPage}
      isPostsLoading={tokenPostsQuery.isLoading}
      isTimelineLoading={tokenTimelineQuery.isFetching}
      postRange={postRange}
      postSortMode={postSortMode}
      posts={tokenPostsData}
      selectedBucketStartMs={selectedBucketStartMs}
      selectedEventId={selectedEventId}
      timeline={tokenTimelineQuery.data?.data}
      token={selectedToken}
      watchedPostsOnly={watchedPostsOnly}
      onHideDuplicateClustersChange={setHideDuplicateClusters}
      onBackToTimeline={handleTimelineBack}
      onDetailWindowChange={handleDetailWindowChange}
      onLoadMorePosts={() => void tokenPostsQuery.fetchNextPage()}
      onPostRangeChange={setPostRange}
      onPostSortModeChange={setPostSortMode}
      onSelectedEventChange={setSelectedEventId}
      onTabChange={handleDetailTabChange}
      onTimelineBucketSelect={handleTimelineBucketSelect}
      onWatchedPostsOnlyChange={setWatchedPostsOnly}
    />
  );

  const layoutElement = (
    <CockpitLayout
      searchInputRef={searchInputRef}
      searchValue={search}
      onSearchChange={setSearch}
      onSubmitSearch={submitEvidenceSearch}
      socketStatus={socket.status}
      lastSocketMessageAt={socket.lastMessageAt}
      status={statusQuery.data?.data ?? null}
      statusLoading={Boolean(token) && statusQuery.isPending}
      statusError={statusQuery.isError}
      configReady={Boolean(token)}
      liveItemsCount={liveItems.length}
      tokenItemsCount={tokenItems.length}
      windowKey={windowKey}
      signalLabSummaryTrade={signalLabOverviewData?.summary.trade_candidate ?? 0}
      signalLabSummaryToken={signalLabOverviewData?.summary.token_watch ?? 0}
      signalLabSummaryTheme={signalLabOverviewData?.summary.theme_watch ?? 0}
      signalLabPulseTotal={signalLabPulseTotal}
      notifications={notifications}
      notificationSummary={notificationSummary}
      notificationDrawerOpen={notificationDrawerOpen}
      onToggleNotificationDrawer={() => setNotificationDrawerOpen((current) => !current)}
      onCloseNotificationDrawer={() => setNotificationDrawerOpen(false)}
      notificationsLoading={notificationsQuery.isFetching && notifications.length === 0}
      onMarkAllRead={() => markAllReadMutation.mutate()}
      onMarkRead={(notificationId) => markReadMutation.mutate(notificationId)}
      onOpenNotification={openNotification}
      socketNotifications={socket.notifications}
      onRefresh={() => void queryClient.invalidateQueries()}
      scope={scope}
      onScopeChange={setScope}
      handles={handles}
      onHandlesChange={setHandles}
      onWindowChange={setWindow}
      decisionCounts={decisionCounts}
      watchlistRows={watchlistRows}
      mobileTask={mobileTask}
      detailAvailable={Boolean(selectedSignal || selectedToken)}
      onMobileTaskChange={handleMobileTaskChange}
      detailPanel={detailPanel}
      onHotkey={handleHotkey}
    />
  );

  const livePageElement = (
    <LivePage
      liveSignalTapeItems={liveSignalTapeItems}
      isRecentLoading={recentQuery.isPending}
      socketStatus={socket.status}
      selectedTapeEventId={selectedTapeEventId}
      onTapeSelect={handleTapeSelect}
      signalLabPulseData={signalLabPulseData ?? null}
      isSignalLabPulseLoading={signalLabPulseQuery.isPending && !signalLabPulseData}
      selectedPulseItemId={selectedPulseItemId}
      onOpenLab={onOpenLab}
      onSelectPulse={selectPulseItem}
    />
  );

  const liveRadarElement = (
    <LiveRadar
      tokenItems={tokenItems}
      isAssetFlowLoading={assetFlowQuery.isPending}
      assetFlowError={assetFlowQuery.error instanceof Error ? assetFlowQuery.error : null}
      selectedTokenKey={selectedTokenKey}
      radarSortMode={radarSortMode}
      onSelectToken={selectToken}
      onOpenToken={openTokenPage}
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
              selectedAccountEventId={selectedAccountEventId}
              overviewData={signalLabOverviewData}
              onSelectAccountEvent={selectAccountEvent}
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

function latestTokenForSelection(signal: Extract<SelectedSignal, { kind: "token" }>, items: TokenFlowItem[]) {
  return items.find((item) => tokenKey(item) === signal.key) ?? null;
}

function latestPulseForSelection(selected: SignalPulseItem, items: SignalPulseItem[]): SignalPulseItem {
  return items.find((item) => item.candidate_id === selected.candidate_id) ?? selected;
}

function signalPulseTotal(summary?: SignalPulseData["summary"]): number {
  if (!summary) {
    return 0;
  }
  return (
    Number(summary.trade_candidate ?? 0) +
    Number(summary.token_watch ?? 0) +
    Number(summary.theme_watch ?? 0) +
    Number(summary.risk_rejected_high_info ?? 0)
  );
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function buildSignalLabUrl({ q, handle }: { q?: string | null; handle?: string | null }): string {
  const params = new URLSearchParams();
  if (handle) {
    params.set("handle", handle);
  }
  if (q) {
    params.set("q", q);
  }
  const search = params.toString();
  return "/signal-lab" + (search ? "?" + search : "");
}

function buildLiveSignalTapeItems({ liveItems, tokenItems }: { liveItems: LivePayload[]; tokenItems: TokenFlowItem[] }): LiveSignalTapeItem[] {
  const byTargetId = new Map<string, TokenFlowItem>();
  const byCa = new Map<string, TokenFlowItem>();
  const byIdentityKey = new Map<string, TokenFlowItem>();
  const bySymbol = new Map<string, TokenFlowItem[]>();
  for (const item of tokenItems) {
    if (item.identity.target_id) {
      byTargetId.set(item.identity.target_id, item);
    }
    byIdentityKey.set(item.identity.identity_key, item);
    const caKey = tokenCaKey(item.identity.chain, item.identity.address);
    if (caKey) {
      byCa.set(caKey, item);
    }
    const symbol = item.identity.symbol?.toUpperCase();
    if (symbol) {
      bySymbol.set(symbol, [...(bySymbol.get(symbol) ?? []), item]);
    }
  }
  const rows: LiveSignalTapeItem[] = [];
  for (const payload of liveItems) {
    const tokenMatch = tokenMatchForPayload(payload, { byTargetId, byCa, byIdentityKey, bySymbol });
    if (tokenMatch) {
      rows.push({
        kind: "token",
        token: tokenMatch,
        event: payload,
        score: tokenMatch.opportunity.score,
        reason: tokenTapeReason(tokenMatch),
        body: eventText(payload.event) || tokenTapeBody(tokenMatch)
      });
    } else {
      rows.push({
        kind: "event",
        payload,
        score: payload.alerts.length ? 80 : null,
        reason: payload.alerts.length ? "watched alert" : "public pulse",
        body: eventText(payload.event)
      });
    }
  }
  for (const item of tokenItems.slice(0, 8)) {
    rows.push({ kind: "token", token: item, event: null, score: item.opportunity.score, reason: tokenTapeReason(item), body: tokenTapeBody(item) });
  }
  const seen = new Set<string>();
  return rows.filter((item) => {
    const id = `${item.kind}:${tapeItemId(item)}`;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

function tokenTapeBody(item: TokenFlowItem): string {
  return [
    `${compactNumber(item.social_heat.mentions)} 帖`,
    `Heat ${compactNumber(item.social_heat.score)}`,
    `作者 ${compactNumber(item.propagation.independent_authors)}`,
    item.timing.status === "market_pending" ? "市场观测处理中" : formatRelativeTime(item.flow.window_end_ms)
  ].join(" · ");
}

function tokenMatchForPayload(
  payload: LivePayload,
  lookup: {
    byTargetId: Map<string, TokenFlowItem>;
    byCa: Map<string, TokenFlowItem>;
    byIdentityKey: Map<string, TokenFlowItem>;
    bySymbol: Map<string, TokenFlowItem[]>;
  }
): TokenFlowItem | undefined {
  for (const resolution of payload.token_resolutions ?? []) {
    if (resolution.target_id && lookup.byTargetId.has(resolution.target_id)) {
      return lookup.byTargetId.get(resolution.target_id);
    }
    if (resolution.target_id && lookup.byIdentityKey.has(resolution.target_id)) {
      return lookup.byIdentityKey.get(resolution.target_id);
    }
    if (resolution.intent_id && lookup.byIdentityKey.has(resolution.intent_id)) {
      return lookup.byIdentityKey.get(resolution.intent_id);
    }
  }
  for (const intent of payload.token_intents ?? []) {
    if (intent.intent_id && lookup.byIdentityKey.has(intent.intent_id)) {
      return lookup.byIdentityKey.get(intent.intent_id);
    }
    const symbol = intent.display_symbol?.toUpperCase();
    const symbolMatches = symbol ? lookup.bySymbol.get(symbol) ?? [] : [];
    if (symbolMatches.length === 1) {
      return symbolMatches[0];
    }
    const caKey = tokenCaKey(intent.chain_hint, intent.address_hint);
    if (caKey && lookup.byCa.has(caKey)) {
      return lookup.byCa.get(caKey);
    }
  }
  for (const entity of payload.entities) {
    if (entity.entity_type !== "ca") {
      continue;
    }
    const caKey = tokenCaKey(entity.chain, entity.normalized_value);
    if (caKey && lookup.byCa.has(caKey)) {
      return lookup.byCa.get(caKey);
    }
  }
  const symbol = payload.event.cashtags?.[0]?.toUpperCase() ?? payload.entities.find((entity) => entity.entity_type === "symbol")?.normalized_value?.toUpperCase();
  const symbolMatches = symbol ? lookup.bySymbol.get(symbol) ?? [] : [];
  return symbolMatches.length === 1 ? symbolMatches[0] : undefined;
}

function tokenCaKey(chain?: string | null, address?: string | null): string | null {
  if (!chain || !address) {
    return null;
  }
  return `${chain.toLowerCase()}:${address.toLowerCase()}`;
}

function patchTokenRadarMarketUpdate(queryClient: QueryClient, update: MarketUpdatePayload) {
  queryClient.setQueriesData<ApiResponse<AssetFlowData>>({ queryKey: ["token-radar"] }, (response) => {
    if (!response?.data) {
      return response;
    }
    const data = patchAssetFlowData(response.data, update);
    return data === response.data ? response : { ...response, data };
  });
}

function patchAssetFlowData(data: AssetFlowData, update: MarketUpdatePayload): AssetFlowData {
  const targets = patchAssetFlowRows(data.targets, update);
  const attention = patchAssetFlowRows(data.attention, update);
  if (targets === data.targets && attention === data.attention) {
    return data;
  }
  return { ...data, targets, attention };
}

function patchAssetFlowRows(rows: AssetFlowRow[], update: MarketUpdatePayload): AssetFlowRow[] {
  let changed = false;
  const next = rows.map((row) => {
    if (!assetFlowRowMatchesMarketUpdate(row, update)) {
      return row;
    }
    changed = true;
    return { ...row, current_market: update.current_market };
  });
  return changed ? next : rows;
}

function assetFlowRowMatchesMarketUpdate(row: AssetFlowRow, update: MarketUpdatePayload): boolean {
  return row.target?.target_type === update.target_type && row.target?.target_id === update.target_id;
}

function tapeItemId(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event?.event.event_id ?? item.token.identity.identity_key;
  }
  return item.payload.event.event_id;
}

function selectedPulseItemIdForSelection(signal: SelectedSignal): string | null {
  if (signal?.kind === "pulse") return signal.item.candidate_id;
  return null;
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
