import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, RefreshCw, Search, UserRound, Wifi, Zap } from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import { getNotifications, getNotificationSummary, markAllNotificationsRead, markNotificationRead } from "./api/notifications";
import type {
  AccountQualityData,
  Decision,
  LivePayload,
  NotificationItem,
  RadarSortMode,
  RecentData,
  SearchData,
  StatusData,
  TokenFlowData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  TradingAttentionData,
  TradingAttentionItem
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
import { WatchlistNotificationDot } from "./components/WatchlistNotificationDot";
import {
  compactNumber,
  eventText,
  formatRelativeTime,
  tokenKey
} from "./lib/format";
import { tokenForSearchQuery } from "./lib/searchIntent";
import { buildWatchlistRows } from "./lib/watchlist";
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

  const tokenFlowQuery = useQuery({
    queryKey: ["token-flow", windowKey, scope],
    queryFn: () =>
      getApi<TokenFlowData>("/api/token-flow", {
        token,
        params: { window: windowKey, limit: 48, scope }
      }),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const tradingAttentionQuery = useInfiniteQuery({
    queryKey: ["signal-lab-pulse", windowKey, signalLabScope, signalLabKind, signalLabHandle, signalLabSearch],
    queryFn: async ({ pageParam }) => {
      const response = await getApi<TradingAttentionData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: windowKey,
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

  const signalLabPulseQuery = useQuery({
    queryKey: ["signal-lab-pulse-compact", signalLabScope],
    queryFn: () =>
      getApi<TradingAttentionData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: "24h",
          scope: signalLabScope,
          limit: 200
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

  const rawTokenItems = tokenFlowQuery.data?.data.items ?? [];
  const tokenItems = useMemo(() => sortTokenItems(rawTokenItems, radarSortMode), [rawTokenItems, radarSortMode]);
  const selectedToken = selectedSignal?.kind === "token" ? latestTokenForSelection(selectedSignal, tokenItems) : null;
  const selectedTokenKey = selectedToken ? tokenKey(selectedToken) : null;
  const tokenTimelineParams = selectedToken ? { ...selectedToken.timeline_query, window: detailWindow } : null;
  const tokenPostRequestSort = postSortMode === "catalyst" ? "catalyst" : "recent";
  const tokenPostParams = selectedToken ? { ...selectedToken.posts_query, window: detailWindow, range: postRange, sort: tokenPostRequestSort } : null;

  const tokenTimelineQuery = useQuery({
    queryKey: ["token-social-timeline", tokenTimelineParams],
    queryFn: () =>
      getApi<TokenSocialTimelineData>("/api/token-social-timeline", {
        token,
        params: tokenTimelineParams ?? {}
      }),
    enabled: Boolean(token && hasTokenIdentity(tokenTimelineParams))
  });

  const tokenPostsQuery = useInfiniteQuery({
    queryKey: ["token-posts", tokenPostParams],
    queryFn: async ({ pageParam }) => {
      const response = await getApi<TokenPostsData>("/api/token-posts", {
        token,
        params: {
          token_id: tokenPostParams?.token_id,
          chain: tokenPostParams?.chain,
          address: tokenPostParams?.address,
          window: tokenPostParams?.window,
          scope: tokenPostParams?.scope,
          range: tokenPostParams?.range,
          sort: tokenPostParams?.sort,
          limit: 24,
          cursor: tokenPostParams?.sort === "catalyst" ? undefined : pageParam || undefined
        }
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.query.sort === "catalyst" ? undefined : lastPage.next_cursor || undefined,
    enabled: Boolean(token && hasTokenIdentity(tokenPostParams))
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
  const signalLabPulseData = signalLabPulseQuery.data?.data ?? tradingAttentionData;
  const tradingAttentionItems = tradingAttentionData?.items ?? [];
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems]
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const tokenPostsData = useMemo(() => mergePostPages(tokenPostsQuery.data?.pages), [tokenPostsQuery.data?.pages]);
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

  const selectAttentionItem = (item: TradingAttentionItem, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "attention", item });
    setSelectedTapeEventId(item.item_id);
    setMobileTask("detail");
    if (options.openLab) {
      setActiveView("signal_lab");
      setMobileTask("lab");
    }
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
        value={tradingAttentionItems.length}
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
            direct <b>{compactNumber(tradingAttentionData?.summary.direct_token ?? 0)}</b>
          </span>
          <span>
            topics <b>{compactNumber(tradingAttentionData?.summary.topic_heat ?? 0)}</b>
          </span>
          <span>
            risk <b>{compactNumber(tradingAttentionData?.summary.risk_alert ?? 0)}</b>
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
            <DecisionCount decision="discard" count={decisionCounts.discard} />
          </RailSection>

          <RailSection label="watchlist" className="watchlist-section">
            <div className="watchlist">
              {watchlistRows.map((row) => (
                <button type="button" key={row.handle} onClick={() => runSearch(`@${row.handle}`)}>
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
                searchFilter={signalLabSearch}
                selectedItemId={selectedAttentionItemId}
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
                <div className="radar-control-row">
                  <RadarControls scope={scope} windowKey={windowKey} onScopeChange={setScope} onWindowChange={setWindow} />
                </div>

                <TokenRadarTable
                  error={tokenFlowQuery.error instanceof Error ? tokenFlowQuery.error : null}
                  isLoading={tokenFlowQuery.isPending}
                  items={tokenItems}
                  selectedKey={selectedTokenKey}
                  sortMode={radarSortMode}
                  onSelect={selectToken}
                  onSortModeChange={setRadarSortMode}
                />
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
    { driver: 0, watch: 0, discard: 0 }
  );
}

function mergePostPages(pages?: TokenPostsData[]): TokenPostsData | null {
  if (!pages?.length) {
    return null;
  }
  const first = pages[0];
  const last = pages[pages.length - 1];
  return {
    ...first,
    returned_count: pages.reduce((total, page) => total + page.returned_count, 0),
    has_more: last.has_more,
    next_cursor: last.next_cursor,
    items: pages.flatMap((page) => page.items)
  };
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
  const byTokenId = new Map<string, TokenFlowItem>();
  const byCa = new Map<string, TokenFlowItem>();
  const byIdentityKey = new Map<string, TokenFlowItem>();
  const bySymbol = new Map<string, TokenFlowItem[]>();
  for (const item of tokenItems) {
    if (item.identity.token_id) {
      byTokenId.set(item.identity.token_id, item);
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
    const tokenMatch = tokenMatchForPayload(payload, { byTokenId, byCa, byIdentityKey, bySymbol });
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

function hasTokenIdentity(params?: { token_id?: string | null; chain?: string | null; address?: string | null } | null): boolean {
  return Boolean(params?.token_id || (params?.chain && params?.address));
}

function tokenMatchForPayload(
  payload: LivePayload,
  lookup: {
    byTokenId: Map<string, TokenFlowItem>;
    byCa: Map<string, TokenFlowItem>;
    byIdentityKey: Map<string, TokenFlowItem>;
    bySymbol: Map<string, TokenFlowItem[]>;
  }
): TokenFlowItem | undefined {
  for (const attribution of payload.token_attributions ?? []) {
    if (attribution.token_id && lookup.byTokenId.has(attribution.token_id)) {
      return lookup.byTokenId.get(attribution.token_id);
    }
    if (attribution.identity_key && lookup.byIdentityKey.has(attribution.identity_key)) {
      return lookup.byIdentityKey.get(attribution.identity_key);
    }
    const caKey = tokenCaKey(attribution.chain, attribution.address);
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
      tokenAttributions: signal.item.token_attributions ?? [],
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
