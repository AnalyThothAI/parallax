import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, RefreshCw, Search, UserRound, Wifi, Zap } from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import { getNotifications, getNotificationSummary, markAllNotificationsRead, markNotificationRead } from "./api/notifications";
import { mergeTokenPostPages, useTokenTargetPosts, useTokenTargetTimeline } from "./api/useTokenTargetQueries";
import type {
  AccountQualityData,
  AssetFlowData,
  AssetFlowRow,
  Decision,
  LivePayload,
  NotificationItem,
  RadarSortMode,
  RiskCap,
  RecentData,
  ScoreContribution,
  SearchData,
  StatusData,
  TimingBlock,
  TokenFlowItem,
  TokenPostRange,
  TokenPostSortMode,
  TradingAttentionData,
  TradingAttentionItem,
  WindowKey
} from "./api/types";
import { useIntelSocket } from "./api/useIntelSocket";
import { EvidenceDetailDrawer, type EvidenceDetailDrawerProps } from "./components/EvidenceDetailDrawer";
import { LiveSignalTape, type LiveSignalTapeItem, tokenTapeReason } from "./components/LiveSignalTape";
import { MobileTaskNav, type MobileTask } from "./components/MobileTaskNav";
import { NotificationBell } from "./components/NotificationBell";
import { NotificationDrawer } from "./components/NotificationDrawer";
import { NotificationToastBridge } from "./components/NotificationToastBridge";
import { SignalLabInspector } from "./components/SignalLabInspector";
import { SignalLabPulse } from "./components/SignalLabPulse";
import { SignalLabWorkbench } from "./components/SignalLabWorkbench";
import { RadarControls } from "./components/RadarControls";
import { TokenDetailDrawer } from "./components/TokenDetailDrawer";
import { TokenRadarTable } from "./components/TokenRadarTable";
import { TokenTargetPage } from "./components/TokenTargetPage";
import { WatchlistNotificationDot } from "./components/WatchlistNotificationDot";
import {
  compactNumber,
  eventText,
  formatRelativeTime,
  tokenKey
} from "./lib/format";
import { tokenForSearchQuery } from "./lib/searchIntent";
import { buildWatchlistRows } from "./lib/watchlist";
import type { TargetRef } from "./domain/tokenTarget";
import { targetRefEquals, targetRefFromTokenItem } from "./domain/tokenTarget";
import { useTraderStore } from "./store/useTraderStore";

type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "attention"; item: TradingAttentionItem }
  | { kind: "query"; query: string }
  | null;

export function App() {
  const queryClient = useQueryClient();
  const windowKey = useTraderStore((state) => state.window);
  const scope = useTraderStore((state) => state.scope);
  const signalLabScope = "matched";
  const signalLabWindow = "24h";
  const signalLabCompactWindow = "1h";
  const handles = useTraderStore((state) => state.handles);
  const search = useTraderStore((state) => state.search);
  const submittedSearch = useTraderStore((state) => state.submittedSearch);
  const token = useTraderStore((state) => state.token);
  const radarSortMode = useTraderStore((state) => state.radarSortMode);
  const detailTab = useTraderStore((state) => state.detailTab);
  const activeView = useTraderStore((state) => state.activeView);
  const signalLabKind = useTraderStore((state) => state.signalLabKind);
  const signalLabHandle = useTraderStore((state) => state.signalLabHandle);
  const signalLabSearch = useTraderStore((state) => state.signalLabSearch);
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
  const setActiveView = useTraderStore((state) => state.setActiveView);
  const setSignalLabKind = useTraderStore((state) => state.setSignalLabKind);
  const setSignalLabHandle = useTraderStore((state) => state.setSignalLabHandle);
  const setSignalLabSearch = useTraderStore((state) => state.setSignalLabSearch);
  const setDetailWindow = useTraderStore((state) => state.setDetailWindow);
  const setDetailMode = useTraderStore((state) => state.setDetailMode);
  const setSelectedBucketStartMs = useTraderStore((state) => state.setSelectedBucketStartMs);
  const setSelectedEventId = useTraderStore((state) => state.setSelectedEventId);
  const setPostRange = useTraderStore((state) => state.setPostRange);
  const setPostSortMode = useTraderStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useTraderStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useTraderStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [pageTargetRef, setPageTargetRef] = useState<TargetRef | null>(null);
  const [pageWindow, setPageWindow] = useState<WindowKey>(windowKey);
  const [pagePostRange, setPagePostRange] = useState<TokenPostRange>("current_window");
  const [pagePostSortMode, setPagePostSortMode] = useState<TokenPostSortMode>("recent");
  const [pageSelectedStageId, setPageSelectedStageId] = useState<string | null>(null);
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
  const socket = useIntelSocket({ token, handles, replay: replayLimit, notifications: true });

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

  const tradingAttentionQuery = useInfiniteQuery({
    queryKey: ["signal-lab-pulse", signalLabWindow, signalLabScope, signalLabKind, signalLabHandle, signalLabSearch],
    queryFn: async ({ pageParam }) => {
      const response = await getApi<TradingAttentionData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: signalLabWindow,
          scope: signalLabScope,
          kind: signalLabKind === "all" ? undefined : signalLabKind,
          handle: signalLabHandle || undefined,
          q: signalLabSearch || undefined,
          limit: 80,
          cursor: pageParam || undefined
        }
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const tradingAttentionOverviewQuery = useQuery({
    queryKey: ["signal-lab-overview", signalLabWindow, signalLabScope],
    queryFn: () =>
      getApi<TradingAttentionData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: signalLabWindow,
          scope: signalLabScope,
          limit: 1
        }
      }),
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const signalLabPulseQuery = useQuery({
    queryKey: ["signal-lab-pulse-compact", signalLabScope, signalLabCompactWindow],
    queryFn: () =>
      getApi<TradingAttentionData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: signalLabCompactWindow,
          scope: signalLabScope,
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
    () => assetFlowRows(assetFlowQuery.data?.data).map((row) => tokenRadarRowToTokenItem(row, windowKey, scope)),
    [assetFlowQuery.data?.data, scope, windowKey]
  );
  const tokenItems = useMemo(() => sortTokenItems(rawTokenItems, radarSortMode), [rawTokenItems, radarSortMode]);
  const selectedToken = selectedSignal?.kind === "token" ? latestTokenForSelection(selectedSignal, tokenItems) : null;
  const selectedTokenKey = selectedToken ? tokenKey(selectedToken) : null;
  const drawerTargetRef = targetRefFromTokenItem(selectedToken);
  const selectedTokenPage = pageTargetRef ? tokenItems.find((item) => targetRefEquals(targetRefFromTokenItem(item), pageTargetRef)) ?? null : null;
  const tokenPostRequestSort = postSortMode === "catalyst" ? "catalyst" : "recent";
  const pagePostRequestSort = pagePostSortMode === "catalyst" ? "catalyst" : "recent";

  const tokenTimelineQuery = useTokenTargetTimeline({ token, target: drawerTargetRef, window: detailWindow, scope });
  const tokenPostsQuery = useTokenTargetPosts({
    token,
    target: drawerTargetRef,
    window: detailWindow,
    scope,
    range: postRange,
    sort: tokenPostRequestSort,
  });
  const pageTimelineQuery = useTokenTargetTimeline({ token, target: pageTargetRef, window: pageWindow, scope });
  const pagePostsQuery = useTokenTargetPosts({
    token,
    target: pageTargetRef,
    window: pageWindow,
    scope,
    range: pagePostRange,
    sort: pagePostRequestSort,
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
  const tradingAttentionData = useMemo(() => mergeTradingAttentionPages(tradingAttentionQuery.data?.pages), [tradingAttentionQuery.data?.pages]);
  const signalLabOverviewData = tradingAttentionOverviewQuery.data?.data ?? signalLabPulseQuery.data?.data ?? tradingAttentionData;
  const signalLabPulseData = signalLabPulseQuery.data?.data ?? signalLabOverviewData;
  const signalLabAttentionTotal = attentionKindTotal(signalLabOverviewData?.summary);
  const tradingAttentionItems = tradingAttentionData?.items ?? [];
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems]
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const tokenPostsData = useMemo(() => mergeTokenPostPages(tokenPostsQuery.data?.pages), [tokenPostsQuery.data?.pages]);
  const pagePostsData = useMemo(() => mergeTokenPostPages(pagePostsQuery.data?.pages), [pagePostsQuery.data?.pages]);
  const selectedAttentionItemId = selectedAttentionItemIdForSelection(selectedSignal);
  const selectedAttentionItem = selectedSignal?.kind === "attention" ? latestAttentionForSelection(selectedSignal.item, tradingAttentionItems) : null;
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
  const watchlistRows = useMemo(
    () =>
      buildWatchlistRows({
        handles: statusQuery.data?.data.handles ?? bootstrapQuery.data?.data.handles ?? [],
        accountUnreadCounts: notificationSummary?.account_unread_counts,
        liveItems
      }),
    [bootstrapQuery.data?.data.handles, liveItems, notificationSummary?.account_unread_counts, statusQuery.data?.data.handles]
  );
  const activeWatchHandle = normalizedHandle(signalLabHandle);

  useEffect(() => {
    if (!latestSocketNotificationId) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }, [latestSocketNotificationId, queryClient]);

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
    if (selectedSignal?.kind !== "attention") {
      return;
    }
    const latest = tradingAttentionItems.find((item) => item.item_id === selectedSignal.item.item_id);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "attention", item: latest });
      return;
    }
    if (!latest && !tradingAttentionQuery.isFetching) {
      setSelectedSignal(null);
    }
  }, [selectedSignal, tradingAttentionItems, tradingAttentionQuery.isFetching]);

  useEffect(() => {
    if (activeView !== "signal_lab" || selectedSignal?.kind === "attention" || !tradingAttentionItems.length) {
      return;
    }
    const preferred = preferredAttentionItem(tradingAttentionItems);
    setSelectedSignal({ kind: "attention", item: preferred });
    setSelectedTapeEventId(preferred.item_id);
  }, [activeView, selectedSignal?.kind, tradingAttentionItems]);

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
    if (!target) {
      return;
    }
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setPageTargetRef(target);
    setPageWindow(windowKey);
    setPagePostRange("current_window");
    setPagePostSortMode("recent");
    setPageSelectedStageId(null);
    setDetailWindow(windowKey);
    setMobileTask("radar");
  };

  const selectAttentionItem = (item: TradingAttentionItem, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "attention", item });
    setSelectedTapeEventId(item.item_id);
    setMobileTask("detail");
    if (options.openLab) {
      setActiveView("signal_lab");
      setMobileTask("lab");
    }
  };

  const clearSignalLabFilters = () => {
    setSignalLabKind("all");
    setSignalLabHandle("");
    setSignalLabSearch("");
    setSelectedSignal(null);
    setSelectedTapeEventId(null);
    setMobileTask("lab");
  };

  const focusWatchHandle = (handle: string) => {
    const normalized = normalizedHandle(handle);
    if (!normalized) {
      return;
    }
    setActiveView("signal_lab");
    setMobileTask("lab");
    setSignalLabKind("all");
    setSignalLabHandle(`@${normalized}`);
    setSignalLabSearch("");
    runSearch(`@${normalized}`);
    setSelectedSignal(null);
    setSelectedTapeEventId(null);
  };

  const submitEvidenceSearch = () => {
    const query = search.trim();
    const tokenMatch = tokenForSearchQuery(query, tokenItems);
    if (tokenMatch) {
      selectToken(tokenMatch);
      return;
    }
    if (activeView === "signal_lab") {
      setSignalLabSearch(query);
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
      setActiveView("live");
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
    if (notification.entity_type === "social_event" || notification.source_table === "social_event_extractions") {
      setActiveView("signal_lab");
      setMobileTask("lab");
      if (notification.symbol) {
        setSignalLabSearch(notification.symbol);
      } else if (notification.author_handle) {
        setSignalLabHandle(notification.author_handle);
      } else if (notification.event_id) {
        setSignalLabSearch(notification.event_id);
      }
      return;
    }
    if (notification.symbol) {
      runSearch(`$${notification.symbol}`);
      setActiveView("live");
      setMobileTask("detail");
      return;
    }
    if (notification.author_handle) {
      runSearch(`@${notification.author_handle}`);
      setActiveView("live");
      setMobileTask("detail");
      return;
    }
    if (notification.event_id) {
      runSearch(notification.event_id);
      setActiveView("live");
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

  const viewControls = (
    <RailSection label="views">
      <RailButton active={activeView === "live"} label="Live" value={liveItems.length} index="1" onClick={() => setActiveView("live")} />
      <RailButton
        active={activeView === "signal_lab"}
        label="Signal Lab"
        value={signalLabAttentionTotal}
        index="2"
        onClick={() => {
          setActiveView("signal_lab");
          setMobileTask("lab");
        }}
      />
    </RailSection>
  );

  const scopeControls = (
    <RailSection label="scope">
      <div className="scope-stack">
        <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">
          watched
        </button>
        <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
          all stream
        </button>
      </div>
      <label className="handle-filter">
        <UserRound aria-hidden />
        <input value={handles} onChange={(event) => setHandles(event.target.value)} placeholder="toly, ansem" />
      </label>
    </RailSection>
  );

  const responsiveControls = (
    <section className="responsive-control-panel" aria-label="cockpit controls">
      <RadarControls
        handles={handles}
        handlePlaceholder="handles"
        scope={scope}
        windowKey={windowKey}
        onHandlesChange={setHandles}
        onScopeChange={setScope}
        onWindowChange={setWindow}
      />
    </section>
  );

  return (
    <main className="cockpit-shell" onKeyDown={handleHotkey} tabIndex={-1}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden />
          <div className="brand-copy">
            <h1>intel.cockpit</h1>
            <p>/ws · localhost:8765</p>
          </div>
        </div>

        <StatusPills
          configReady={Boolean(token)}
          lastMessageAt={socket.lastMessageAt}
          socketStatus={socket.status}
          status={statusQuery.data?.data}
          statusError={statusQuery.isError}
          statusLoading={Boolean(token) && statusQuery.isPending}
        />

        <form
          className="searchbar"
          onSubmit={(event) => {
            event.preventDefault();
            submitEvidenceSearch();
          }}
        >
          <Search aria-hidden />
          <input
            ref={searchInputRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索 CA / $TOKEN / @handle / 文本"
          />
          <button type="submit">检索</button>
        </form>

        <div className="top-stats">
          <span>
            MATCHED <b>{compactNumber(statusQuery.data?.data.collector.matched_twitter_events)}</b>
          </span>
          <span>
            flow·{windowKey} <b>{compactNumber(tokenItems.length)}</b>
          </span>
          <span>
            direct <b>{compactNumber(signalLabOverviewData?.summary.direct_token ?? 0)}</b>
          </span>
          <span>
            topics <b>{compactNumber(signalLabOverviewData?.summary.topic_heat ?? 0)}</b>
          </span>
          <span>
            risk <b>{compactNumber(signalLabOverviewData?.summary.risk_alert ?? 0)}</b>
          </span>
        </div>

        <NotificationBell
          open={notificationDrawerOpen}
          summary={notificationSummary}
          onClick={() => setNotificationDrawerOpen((current) => !current)}
        />

        <button className="icon-button" type="button" onClick={() => void queryClient.invalidateQueries()} title="刷新" aria-label="刷新">
          <RefreshCw aria-hidden />
        </button>
      </header>

      <div className={`cockpit-grid mobile-task-${mobileTask} ${activeView === "signal_lab" ? "signal-lab-mode" : ""}`}>
        <aside className="side-rail desktop-side-rail">
          {viewControls}
          {scopeControls}

          <RailSection label="decisions">
            <DecisionCount decision="driver" count={decisionCounts.driver} />
            <DecisionCount decision="watch" count={decisionCounts.watch} />
            <DecisionCount decision="investigate" count={decisionCounts.investigate} />
            <DecisionCount decision="discard" count={decisionCounts.discard} />
          </RailSection>

          <RailSection label="watchlist" className="watchlist-section">
            <div className="watchlist">
              {watchlistRows.map((row) => (
                <button
                  className={activeView === "signal_lab" && activeWatchHandle === row.handle ? "active" : ""}
                  type="button"
                  key={row.handle}
                  onClick={() => focusWatchHandle(row.handle)}
                >
                  <span className="watchlist-avatar">{row.handle.slice(0, 1).toUpperCase()}</span>
                  <span className="watchlist-copy">
                    <b>@{row.handle}</b>
                    <small>{row.lastSeenAtMs ? `${formatRelativeTime(row.lastSeenAtMs)} ago` : "no recent"}</small>
                  </span>
                  <WatchlistNotificationDot count={row.unreadCount} />
                </button>
              ))}
            </div>
          </RailSection>

          <div className="rail-footer">
            <span>kbd · 1-4 radar · / search</span>
          </div>
        </aside>

        {responsiveControls}

        <section className="center-column">
          {activeView === "signal_lab" ? (
            <section className="mobile-task-surface signal-lab-task-surface" data-mobile-task-panel="lab">
              <SignalLabWorkbench
                data={tradingAttentionData}
                handleFilter={signalLabHandle}
                isLoading={tradingAttentionQuery.isPending}
                isFetchingNextPage={tradingAttentionQuery.isFetchingNextPage}
                hasNextPage={Boolean(tradingAttentionQuery.hasNextPage)}
                kindFilter={signalLabKind}
                overviewData={signalLabOverviewData}
                searchFilter={signalLabSearch}
                selectedItemId={selectedAttentionItemId}
                windowLabel={signalLabWindow}
                onClearFilters={clearSignalLabFilters}
                onHandleChange={setSignalLabHandle}
                onKindChange={setSignalLabKind}
                onLoadMore={() => void tradingAttentionQuery.fetchNextPage()}
                onSearchChange={setSignalLabSearch}
                onSelect={selectAttentionItem}
              />
            </section>
          ) : (
            <>
              <section className="mobile-task-surface" data-mobile-task-panel="radar">
                {selectedTokenPage ? (
                  <TokenTargetPage
                    token={selectedTokenPage}
                    timeline={pageTimelineQuery.data?.data ?? null}
                    posts={pagePostsData}
                    windowKey={pageWindow}
                    postRange={pagePostRange}
                    postSortMode={pagePostSortMode}
                    selectedStageId={pageSelectedStageId}
                    isTimelineLoading={pageTimelineQuery.isFetching}
                    isPostsLoading={pagePostsQuery.isLoading}
                    isPostsFetchingNextPage={pagePostsQuery.isFetchingNextPage}
                    onBack={() => setPageTargetRef(null)}
                    onWindowChange={setPageWindow}
                    onPostRangeChange={setPagePostRange}
                    onPostSortModeChange={setPagePostSortMode}
                    onStageSelect={setPageSelectedStageId}
                    onLoadMorePosts={() => void pagePostsQuery.fetchNextPage()}
                  />
                ) : (
                  <>
                    <div className="radar-control-row">
                      <RadarControls scope={scope} windowKey={windowKey} onScopeChange={setScope} onWindowChange={setWindow} />
                    </div>

                    <TokenRadarTable
                      error={assetFlowQuery.error instanceof Error ? assetFlowQuery.error : null}
                      isLoading={assetFlowQuery.isPending}
                      items={tokenItems}
                      selectedKey={selectedTokenKey}
                      sortMode={radarSortMode}
                      onSelect={selectToken}
                      onOpenPage={openTokenPage}
                      onSortModeChange={setRadarSortMode}
                    />
                  </>
                )}
              </section>

              <div className="bottom-deck">
                <LiveSignalTape
                  isLoading={recentQuery.isPending}
                  items={liveSignalTapeItems}
                  mobileTaskPanel="tape"
                  selectedEventId={selectedTapeEventId}
                  socketStatus={socket.status}
                  onSelect={handleTapeSelect}
                />

                <SignalLabPulse
                  data={signalLabPulseData}
                  isLoading={signalLabPulseQuery.isPending && !signalLabPulseData}
                  mobileTaskPanel="lab"
                  selectedItemId={selectedAttentionItemId}
                  onOpenLab={() => {
                    setActiveView("signal_lab");
                    setMobileTask("lab");
                  }}
                  onSelect={selectAttentionItem}
                />
              </div>
            </>
          )}
        </section>

        <section className="detail-task-panel" data-mobile-task-panel="detail">
          {selectedAttentionItem ? (
            <SignalLabInspector item={selectedAttentionItem} />
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
              isSignalLabLoading={tradingAttentionQuery.isFetching}
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
          )}
        </section>
      </div>
      <MobileTaskNav
        activeTask={mobileTask}
        detailAvailable={Boolean(selectedSignal || selectedToken)}
        onTaskChange={handleMobileTaskChange}
      />
      <NotificationDrawer
        loading={notificationsQuery.isFetching && notifications.length === 0}
        notifications={notifications}
        open={notificationDrawerOpen}
        summary={notificationSummary}
        onClose={() => setNotificationDrawerOpen(false)}
        onMarkAllRead={() => markAllReadMutation.mutate()}
        onMarkRead={(notificationId) => markReadMutation.mutate(notificationId)}
        onOpenNotification={openNotification}
      />
      <NotificationToastBridge
        notifications={socket.notifications.map((item) => item.notification)}
        onOpenNotification={openNotification}
      />
    </main>
  );
}

function RailSection({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rail-section ${className}`.trim()}>
      <h2>{label}</h2>
      {children}
    </section>
  );
}

function RailButton({ active, label, value, index, onClick }: { active?: boolean; label: string; value: number; index: string; onClick: () => void }) {
  return (
    <button className={`rail-button ${active ? "active" : ""}`} type="button" onClick={onClick}>
      <span>{index}</span>
      <b>{label}</b>
      <em>{compactNumber(value)}</em>
    </button>
  );
}

function DecisionCount({ decision, count }: { decision: Decision; count: number }) {
  return (
    <span className={`decision-count ${decision}`}>
      <span className={`decision-tag ${decision}`}>{decision}</span>
      <b>{compactNumber(count)}</b>
    </span>
  );
}

function StatusPills({
  socketStatus,
  configReady,
  status,
  statusLoading,
  statusError,
  lastMessageAt
}: {
  socketStatus: string;
  configReady: boolean;
  status?: StatusData;
  statusLoading: boolean;
  statusError: boolean;
  lastMessageAt: number | null;
}) {
  const readiness = readinessLabel({ configReady, status, statusLoading, statusError });
  return (
    <div className="status-pills">
      <span className={configReady ? "pill good" : "pill warn"}>
        <Zap aria-hidden />
        {configReady ? "token ready" : "token"}
      </span>
      <span className={socketStatus === "connected" ? "pill good" : "pill warn"}>
        <Wifi aria-hidden />
        {socketStatus}
      </span>
      <span className={readiness.ok ? "pill good" : "pill warn"} title={readiness.title}>
        <Zap aria-hidden />
        {readiness.label}
      </span>
      <span className="pill muted">
        <Clock3 aria-hidden />
        {lastMessageAt ? `${formatRelativeTime(lastMessageAt)} ago` : "no msg"}
      </span>
    </div>
  );
}

function readinessLabel({
  configReady,
  status,
  statusLoading,
  statusError
}: {
  configReady: boolean;
  status?: StatusData;
  statusLoading: boolean;
  statusError: boolean;
}): { label: string; ok: boolean; title?: string } {
  if (!configReady) {
    return { label: "status idle", ok: false };
  }
  if (statusLoading && !status) {
    return { label: "checking", ok: false };
  }
  if (statusError) {
    return { label: "status error", ok: false };
  }
  if (status?.ok) {
    return { label: "ready", ok: true };
  }
  return {
    label: "not ready",
    ok: false,
    title: status?.reasons?.join(", ") || undefined
  };
}

function sortTokenItems(items: TokenFlowItem[], mode: RadarSortMode): TokenFlowItem[] {
  const copy = [...items];
  return copy.sort((a, b) => sortValue(b, mode) - sortValue(a, mode));
}

function sortValue(item: TokenFlowItem, mode: RadarSortMode): number {
  if (mode === "heat") return item.social_heat.score;
  if (mode === "quality") return item.discussion_quality.score;
  if (mode === "propagation") return item.propagation.score;
  if (mode === "timing") return (item.timing.chase_risk ? -1000 : 0) + item.timing.score;
  return item.opportunity.score;
}

function latestTokenForSelection(signal: Extract<SelectedSignal, { kind: "token" }>, items: TokenFlowItem[]) {
  return items.find((item) => tokenKey(item) === signal.key) ?? null;
}

function latestAttentionForSelection(selected: TradingAttentionItem, items: TradingAttentionItem[]): TradingAttentionItem {
  return items.find((item) => item.item_id === selected.item_id) ?? selected;
}

function countDecisions(items: TokenFlowItem[]): Record<Decision, number> {
  return items.reduce<Record<Decision, number>>(
    (counts, item) => {
      counts[item.opportunity.decision] += 1;
      return counts;
    },
    { driver: 0, watch: 0, investigate: 0, discard: 0 }
  );
}

function assetFlowRows(data?: AssetFlowData | null): AssetFlowRow[] {
  if (!data) {
    return [];
  }
  return [...data.targets, ...data.attention];
}

export function tokenRadarRowToTokenItem(row: AssetFlowRow, window: TokenFlowItem["flow"]["window"], scope: TokenFlowItem["posts_query"]["scope"]): TokenFlowItem {
  const mentions = row.attention.mentions_window;
  const authors = row.attention.unique_authors;
  const watched = row.attention.watched_mentions;
  const previousMentions = row.attention.previous_mentions ?? 0;
  const mentionDelta = row.attention.mention_delta ?? mentions;
  const mentionDeltaPct = row.attention.mention_delta_pct ?? null;
  const zScore = row.attention.z_score ?? null;
  const newBurstScore = row.attention.new_burst_score ?? null;
  const streamShare = row.attention.stream_share ?? 0;
  const resolved = isResolvedResolutionStatus(row.resolution.status);
  const price = row.price ?? null;
  const target = row.target ?? {};
  const isChainAsset = target.target_type === "Asset";
  const isCexToken = target.target_type === "CexToken";
  const displaySymbol = row.intent?.display_symbol ?? target.symbol ?? null;
  const targetId = target.target_id ?? row.resolution.target_id ?? null;
  const identityKey = targetId ?? row.intent?.intent_id ?? target.address ?? target.native_market_id ?? displaySymbol ?? "unknown-token-intent";
  const resolutionReasons = row.resolution.reason_codes ?? row.resolution.reasons ?? [];
  const candidateCount = row.resolution.candidate_ids?.length ?? row.resolution.candidates?.length ?? 0;
  const discoveryStatus = discoveryStatusSummary(row.resolution.discovery);
  const marketObservationStatus = price?.market_observation_status ?? row.data_health?.market ?? "missing_market";
  const marketHasUsableSnapshot = price?.market_status === "ready" || price?.market_status === "fresh";
  const priceChangeStatus = price?.price_change_status ?? (marketHasUsableSnapshot ? "ready" : "missing_market");
  const heat = normalizedScoreBlock(row.score?.heat);
  const quality = normalizedScoreBlock(row.score?.quality);
  const propagation = normalizedScoreBlock(row.score?.propagation);
  const tradeability = normalizedScoreBlock(row.score?.tradeability);
  const timing = normalizedScoreBlock(row.score?.timing);
  const opportunity = normalizedScoreBlock(row.score?.opportunity);
  const decision = normalizeDecision(row.decision);
  const timingStatus = normalizeTimingStatus(timing.status ?? timing.reasons[0], resolved);
  const chaseRisk = Boolean(timing.chase_risk ?? timing.hard_risks?.includes("chase_risk") ?? timing.risks.includes("chase_risk"));
  const marketPrice = price?.price_usd ?? price?.price_quote ?? null;
  const chain = isChainAsset ? target.chain_id ?? null : null;
  const address = isChainAsset ? target.address ?? null : null;
  return {
    identity: {
      identity_key: identityKey,
      identity_status: row.resolution.status,
      target_type: target.target_type ?? null,
      target_id: targetId,
      asset_id: isChainAsset ? targetId ?? undefined : undefined,
      asset_type: target.target_type ?? null,
      venue_type: isCexToken ? "cex" : isChainAsset ? "dex" : null,
      exchange: isCexToken ? target.provider ?? null : null,
      inst_id: isCexToken ? target.native_market_id ?? null : null,
      inst_type: isCexToken ? target.feed_type ?? null : null,
      chain,
      address,
      symbol: displaySymbol,
      resolution_reasons: resolutionReasons,
      lookup_keys: row.resolution.lookup_keys ?? [],
      candidate_count: candidateCount,
      discovery_status: discoveryStatus
    },
    market: {
      market_status: price?.market_status ?? "missing",
      price: marketPrice,
      market_cap: price?.market_cap_usd ?? null,
      liquidity: price?.liquidity_usd ?? null,
      pool_status: marketHasUsableSnapshot ? "ready" : "missing",
      holder_count: price?.holders ?? null,
      volume_24h: price?.volume_24h_usd ?? null,
      snapshot_age_ms: price?.snapshot_age_ms ?? null,
      snapshot_received_at_ms: price?.snapshot_observed_at_ms ?? null,
      social_signal_start_ms: price?.social_signal_start_ms ?? row.attention.latest_seen_ms ?? null,
      reference_ms: row.attention.latest_seen_ms ?? null,
      price_at_social_start: price?.price_at_social_start ?? null,
      price_at_reference: price?.price_at_reference ?? marketPrice,
      price_change_since_social_pct: price?.price_change_since_social_pct ?? null,
      price_before_social_start: price?.price_before_social_start ?? null,
      price_change_before_social_pct: price?.price_change_before_social_pct ?? null,
      price_at_first_snapshot: price?.price_at_first_snapshot ?? null,
      first_snapshot_observed_at_ms: price?.first_snapshot_observed_at_ms ?? null,
      price_change_since_first_snapshot_pct: price?.price_change_since_first_snapshot_pct ?? null,
      market_observation_status: marketObservationStatus,
      price_change_status: priceChangeStatus
    },
    flow: {
      window,
      window_start_ms: null,
      window_end_ms: row.attention.latest_seen_ms ?? null,
      mentions,
      direct_mentions: resolved ? mentions : 0,
      symbol_mentions: mentions,
      weighted_mentions: mentions,
      avg_attribution_confidence: row.resolution.confidence ?? undefined,
      watched_mentions: watched,
      previous_mentions: previousMentions,
      mention_delta: mentionDelta,
      mention_delta_pct: mentionDeltaPct,
      z_score: zScore,
      new_burst_score: newBurstScore,
      stream_dominance: 0,
      baseline_status: row.attention.baseline_status ?? "insufficient_history",
      baseline_sample_count: row.attention.baseline_sample_count ?? 0
    },
    social_heat: {
      ...heat,
      window,
      mentions,
      mentions_5m: row.attention.mentions_5m,
      mentions_1h: row.attention.mentions_1h,
      mentions_4h: window === "4h" ? mentions : row.attention.mentions_1h,
      mentions_24h: window === "24h" ? mentions : row.attention.mentions_1h,
      weighted_mentions: mentions,
      previous_mentions: previousMentions,
      mention_delta: mentionDelta,
      mention_delta_pct: mentionDeltaPct,
      z_score: zScore,
      new_burst_score: newBurstScore,
      stream_share: streamShare,
      watched_share: mentions ? watched / mentions : 0,
      status: heat.reasons[0] ?? (newBurstScore !== null ? "rising" : "insufficient_history")
    },
    discussion_quality: {
      ...quality,
      evidence_specificity: 0,
      avg_post_quality: quality.score,
      avg_attribution_confidence: row.resolution.confidence ?? 0,
      duplicate_text_share: 0,
      informative_post_count: Math.min(mentions, authors || mentions),
      watched_source_count: watched
    },
    propagation: {
      ...propagation,
      independent_authors: authors,
      effective_authors: authors,
      new_authors: authors,
      top_author_share: authors ? 1 / authors : 0,
      duplicate_text_share: 0,
      author_entropy: authors > 1 ? 1 : 0,
      reproduction_rate: null,
      phase: authors >= 3 ? "expansion" : authors >= 2 ? "ignition" : "seed",
      top_authors: []
    },
    tradeability: {
      ...tradeability,
      identity_tradeable: Boolean(tradeability.identity_tradeable ?? resolved),
      market_fresh: Boolean(tradeability.market_fresh ?? marketHasUsableSnapshot),
      market_cap_present: Boolean(tradeability.market_cap_present ?? price?.market_cap_usd),
      liquidity_present: Boolean(tradeability.liquidity_present ?? price?.liquidity_usd),
      pool_present: Boolean(tradeability.pool_present ?? marketHasUsableSnapshot),
      hard_risks: tradeability.hard_risks ?? tradeability.risks
    },
    timing: {
      score: timing.score,
      score_version: timing.score_version,
      status: timingStatus,
      social_signal_start_ms: row.attention.latest_seen_ms ?? null,
      price_change_since_social_pct: price?.price_change_since_social_pct ?? null,
      price_change_before_social_pct: price?.price_change_before_social_pct ?? null,
      market_observation_status: marketObservationStatus,
      chase_risk: chaseRisk,
      reasons: timing.reasons,
      risks: timing.risks,
      contributions: timing.contributions,
      risk_caps: timing.risk_caps
    },
    opportunity: {
      ...opportunity,
      decision,
      decision_priority: decision === "driver" ? 3 : decision === "watch" ? 2 : 1,
      hard_risks: opportunity.hard_risks ?? opportunity.risks,
      components: {
        heat: row.score?.opportunity?.components?.heat ?? heat.score,
        quality: row.score?.opportunity?.components?.quality ?? quality.score,
        propagation: row.score?.opportunity?.components?.propagation ?? propagation.score,
        tradeability: row.score?.opportunity?.components?.tradeability ?? tradeability.score,
        timing: row.score?.opportunity?.components?.timing ?? timing.score
      }
    },
    watch: {
      status: watched ? "direct_watch" : "public_only",
      direct_mentions: watched,
      direct_authors: watched ? 1 : 0,
      seed_link_count: 0,
      top_seed: null,
      reasons: watched ? ["watched_source_present"] : [],
      risks: watched ? [] : ["no_watched_confirmation"]
    },
    evidence_total_count: row.source_event_ids?.length ?? mentions,
    posts_query: { target_type: target.target_type ?? null, target_id: targetId, window, scope, range: "current_window" },
    timeline_query: { target_type: target.target_type ?? null, target_id: targetId, window, scope }
  };
}

function isResolvedResolutionStatus(status?: string | null): boolean {
  return status === "EXACT" || status === "UNIQUE_BY_CONTEXT";
}

type RadarScoreInput = {
  score?: number | null;
  score_version?: string | null;
  reasons?: string[];
  risks?: string[];
  hard_risks?: string[];
  contributions?: ScoreContribution[];
  risk_caps?: RiskCap[];
  status?: string | null;
  chase_risk?: boolean | null;
};

function normalizedScoreBlock(block: RadarScoreInput | undefined): any {
  const extra = block && typeof block === "object" ? { ...block } : {};
  return {
    ...extra,
    score: Math.round(Number(block?.score ?? 0)),
    score_version: block?.score_version ?? "missing_score_version",
    reasons: block?.reasons ?? [],
    risks: block?.risks ?? [],
    hard_risks: block?.hard_risks ?? [],
    contributions: block?.contributions ?? [],
    risk_caps: block?.risk_caps ?? [],
    status: block?.status ?? undefined,
    chase_risk: block?.chase_risk ?? undefined
  };
}

function normalizeDecision(value: string | null | undefined): Decision {
  return value === "driver" || value === "watch" || value === "investigate" || value === "discard" ? value : "investigate";
}

function normalizeTimingStatus(value: string | null | undefined, resolved: boolean): TimingBlock["status"] {
  if (value === "neutral" || value === "market_pending" || value === "market_unavailable" || value === "chase_risk") {
    return value;
  }
  return resolved ? "neutral" : "market_unavailable";
}

function discoveryStatusSummary(discovery: AssetFlowRow["resolution"]["discovery"]): string | null {
  if (!discovery?.length) {
    return null;
  }
  const statuses = Array.from(new Set(discovery.map((item) => item.status).filter(Boolean)));
  if (statuses.length === 1) {
    const candidateTotal = discovery.reduce((sum, item) => sum + Number(item.candidate_count ?? 0), 0);
    return candidateTotal > 0 ? `${statuses[0]}:${candidateTotal}` : String(statuses[0]);
  }
  return statuses.join("+");
}

function attentionKindTotal(summary?: TradingAttentionData["summary"]): number {
  if (!summary) {
    return 0;
  }
  return (
    Number(summary.direct_token ?? 0) +
    Number(summary.topic_heat ?? 0) +
    Number(summary.ecosystem_signal ?? 0) +
    Number(summary.market_structure ?? 0) +
    Number(summary.risk_alert ?? 0)
  );
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function mergeTradingAttentionPages(pages?: TradingAttentionData[]): TradingAttentionData | undefined {
  if (!pages?.length) {
    return undefined;
  }
  const first = pages[0];
  const last = pages[pages.length - 1];
  const items = pages.flatMap((page) => page.items);
  const summary = pages.reduce<TradingAttentionData["summary"]>(
    (counts, page) => {
      for (const [key, value] of Object.entries(page.summary)) {
        counts[key as keyof TradingAttentionData["summary"]] = (counts[key as keyof TradingAttentionData["summary"]] ?? 0) + value;
      }
      return counts;
    },
    {
      direct_token: 0,
      topic_heat: 0,
      ecosystem_signal: 0,
      market_structure: 0,
      risk_alert: 0,
      low_signal: 0,
      hot: 0,
      watch: 0,
      context: 0,
      muted: 0
    }
  );
  return {
    ...first,
    summary,
    returned_count: items.length,
    has_more: last.has_more,
    next_cursor: last.next_cursor,
    items
  };
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

function tapeItemId(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event?.event.event_id ?? item.token.identity.identity_key;
  }
  return item.payload.event.event_id;
}

function selectedAttentionItemIdForSelection(signal: SelectedSignal): string | null {
  if (signal?.kind === "attention") return signal.item.item_id;
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

function preferredAttentionItem(items: TradingAttentionItem[]): TradingAttentionItem {
  return [...items].sort(
    (a, b) =>
      attentionPriorityRank(b) - attentionPriorityRank(a) ||
      b.heat_score - a.heat_score ||
      b.updated_at_ms - a.updated_at_ms
  )[0];
}

function attentionPriorityRank(item: TradingAttentionItem): number {
  if (item.priority === "hot") return 4;
  if (item.priority === "watch") return 3;
  if (item.priority === "context") return 2;
  return 1;
}
