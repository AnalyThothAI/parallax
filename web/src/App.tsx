import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, RefreshCw, Search, UserRound, Wifi, Zap } from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import type {
  AccountAlertsData,
  AccountQualityData,
  AlertRecord,
  Decision,
  HarnessHealth,
  HarnessHealthData,
  LivePayload,
  RadarSortMode,
  RecentData,
  SearchData,
  SignalLabChain,
  SignalLabChainsData,
  StatusData,
  TokenFlowData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey
} from "./api/types";
import { useIntelSocket } from "./api/useIntelSocket";
import { EvidenceDetailDrawer, type EvidenceDetailDrawerProps } from "./components/EvidenceDetailDrawer";
import { LiveSignalTape, type LiveSignalTapeItem, tokenTapeReason } from "./components/LiveSignalTape";
import { MobileTaskNav, type MobileTask } from "./components/MobileTaskNav";
import { SignalLabInspector } from "./components/SignalLabInspector";
import { SignalLabPulse } from "./components/SignalLabPulse";
import { SignalLabWorkbench } from "./components/SignalLabWorkbench";
import { TokenDetailDrawer } from "./components/TokenDetailDrawer";
import { TokenRadarTable } from "./components/TokenRadarTable";
import {
  compactNumber,
  eventText,
  formatRelativeTime,
  tokenKey
} from "./lib/format";
import { tokenForSearchQuery } from "./lib/searchIntent";
import { totalChains } from "./lib/signalLabChains";
import { useTraderStore } from "./store/useTraderStore";

const WINDOWS: WindowKey[] = ["5m", "1h", "24h"];
const ACCOUNT_ALERT_WINDOW: WindowKey = "24h";

type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "signal_chain"; item: SignalLabChain }
  | { kind: "alert"; item: AlertRecord }
  | { kind: "query"; query: string }
  | null;

export function App() {
  const queryClient = useQueryClient();
  const windowKey = useTraderStore((state) => state.window);
  const scope = useTraderStore((state) => state.scope);
  const handles = useTraderStore((state) => state.handles);
  const search = useTraderStore((state) => state.search);
  const submittedSearch = useTraderStore((state) => state.submittedSearch);
  const token = useTraderStore((state) => state.token);
  const radarSortMode = useTraderStore((state) => state.radarSortMode);
  const detailTab = useTraderStore((state) => state.detailTab);
  const activeView = useTraderStore((state) => state.activeView);
  const signalLabStage = useTraderStore((state) => state.signalLabStage);
  const signalLabHorizon = useTraderStore((state) => state.signalLabHorizon);
  const signalLabAsset = useTraderStore((state) => state.signalLabAsset);
  const signalLabHandle = useTraderStore((state) => state.signalLabHandle);
  const signalLabSearch = useTraderStore((state) => state.signalLabSearch);
  const signalLabInspectorTab = useTraderStore((state) => state.signalLabInspectorTab);
  const timelineBucket = useTraderStore((state) => state.timelineBucket);
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
  const setSignalLabStage = useTraderStore((state) => state.setSignalLabStage);
  const setSignalLabHorizon = useTraderStore((state) => state.setSignalLabHorizon);
  const setSignalLabAsset = useTraderStore((state) => state.setSignalLabAsset);
  const setSignalLabHandle = useTraderStore((state) => state.setSignalLabHandle);
  const setSignalLabInspectorTab = useTraderStore((state) => state.setSignalLabInspectorTab);
  const setSignalLabSearch = useTraderStore((state) => state.setSignalLabSearch);
  const setTimelineBucket = useTraderStore((state) => state.setTimelineBucket);
  const setPostSortMode = useTraderStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useTraderStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useTraderStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
  const [mobileTask, setMobileTask] = useState<MobileTask>("radar");
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
  const socket = useIntelSocket({ token, handles, replay: replayLimit });

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

  const alertsQuery = useQuery({
    queryKey: ["account-alerts", ACCOUNT_ALERT_WINDOW, handles],
    queryFn: () =>
      getApi<AccountAlertsData>("/api/account-alerts", {
        token,
        params: { window: ACCOUNT_ALERT_WINDOW, limit: 80, handles }
      }),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const signalLabHealthQuery = useQuery({
    queryKey: ["harness-health"],
    queryFn: () => getApi<HarnessHealthData>("/api/harness-health", { token }),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const signalLabChainsQuery = useInfiniteQuery({
    queryKey: ["signal-lab-chains", windowKey, signalLabHorizon, scope, signalLabStage, signalLabAsset, signalLabHandle, signalLabSearch],
    queryFn: async ({ pageParam }) => {
      const response = await getApi<SignalLabChainsData>("/api/signal-lab/chains", {
        token,
        params: {
          window: windowKey,
          horizon: signalLabHorizon,
          scope,
          stage: signalLabStage === "all" ? undefined : signalLabStage,
          asset: signalLabAsset || undefined,
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
  const tokenTimelineParams = selectedToken ? { ...selectedToken.timeline_query, bucket: timelineBucket } : null;
  const tokenPostParams = selectedToken ? selectedToken.posts_query : null;

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
          limit: 24,
          cursor: pageParam || undefined
        }
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
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
  const signalLabHealth = signalLabHealthQuery.data?.data ?? defaultSignalLabHealth(statusQuery.data?.data);
  const signalLabData = useMemo(() => mergeSignalLabPages(signalLabChainsQuery.data?.pages), [signalLabChainsQuery.data?.pages]);
  const signalLabChains = signalLabData?.items ?? [];
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems]
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const tokenPostsData = useMemo(() => mergePostPages(tokenPostsQuery.data?.pages), [tokenPostsQuery.data?.pages]);
  const selectedSignalChainId = selectedSignalChainIdForSelection(selectedSignal);
  const selectedSignalChain = selectedSignal?.kind === "signal_chain" ? latestSignalChainForSelection(selectedSignal.item, signalLabChains) : null;
  const selectedEvidenceDetails = useMemo(
    () =>
      resolveEvidenceDetails(selectedSignal, {
        currentSearchData,
        searchError: searchQuery.error instanceof Error ? searchQuery.error : null,
        searchFetching: searchQuery.isFetching
      }),
    [currentSearchData, searchQuery.error, searchQuery.isFetching, selectedSignal]
  );
  const selectedTokenSignalChains = useMemo(() => filterSignalChainsForToken(selectedToken, signalLabChains), [selectedToken, signalLabChains]);

  useEffect(() => {
    if (!selectedSignal && tokenItems.length) {
      setSelectedSignal({ kind: "token", key: tokenKey(tokenItems[0]), item: tokenItems[0] });
      setDetailTab("timeline");
    }
  }, [selectedSignal, setDetailTab, tokenItems]);

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
      return;
    }
    if (!latest) {
      setSelectedSignal(null);
    }
  }, [selectedSignal, setDetailTab, tokenItems]);

  useEffect(() => {
    if (selectedSignal?.kind !== "signal_chain") {
      return;
    }
    const latest = signalLabChains.find((item) => item.chain_id === selectedSignal.item.chain_id);
    if (latest && latest !== selectedSignal.item) {
      setSelectedSignal({ kind: "signal_chain", item: latest });
      return;
    }
    if (!latest && !signalLabChainsQuery.isFetching) {
      setSelectedSignal(null);
    }
  }, [selectedSignal, signalLabChains, signalLabChainsQuery.isFetching]);

  useEffect(() => {
    if (activeView !== "signal_lab" || selectedSignal?.kind === "signal_chain" || !signalLabChains.length) {
      return;
    }
    const preferred = preferredSignalChain(signalLabChains);
    setSelectedSignal({ kind: "signal_chain", item: preferred });
    setSignalLabInspectorTab("trace");
    setSelectedTapeEventId(preferred.chain_id);
  }, [activeView, selectedSignal?.kind, setSignalLabInspectorTab, signalLabChains]);

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailTab("timeline");
    setSelectedTapeEventId(tapeId);
    setMobileTask("detail");
  };

  const selectSignalChain = (item: SignalLabChain, options: { openLab?: boolean } = {}) => {
    setSelectedSignal({ kind: "signal_chain", item });
    setSignalLabInspectorTab("trace");
    setSelectedTapeEventId(item.chain_id);
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
      setSelectedTapeEventId(null);
      setMobileTask("radar");
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
    if (event.key === "3") setWindow("24h");
  };

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
            seeded <b>{compactNumber(signalLabData?.summary.seeded ?? 0)}</b>
          </span>
          <span>
            frozen <b>{compactNumber(signalLabData?.summary.frozen ?? 0)}</b>
          </span>
          <span>
            settled <b>{formatSignalLabCoverage(signalLabHealth.settlement_coverage)}</b>
          </span>
        </div>

        <button className="icon-button" type="button" onClick={() => void queryClient.invalidateQueries()} title="刷新" aria-label="刷新">
          <RefreshCw aria-hidden />
        </button>
      </header>

      <div className={`cockpit-grid mobile-task-${mobileTask} ${activeView === "signal_lab" ? "signal-lab-mode" : ""}`}>
        <aside className="side-rail">
          <RailSection label="views">
            <RailButton active={activeView === "live"} label="Live" value={liveItems.length} index="1" onClick={() => setActiveView("live")} />
            <RailButton
              active={activeView === "signal_lab"}
              label="Signal Lab"
              value={totalChains(signalLabData?.summary, signalLabChains.length)}
              index="2"
              onClick={() => setActiveView("signal_lab")}
            />
          </RailSection>

          <RailSection label="window">
            <div className="window-stack">
              {WINDOWS.map((item, index) => (
                <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
                  {index + 1}<span>{item}</span>
                </button>
              ))}
            </div>
          </RailSection>

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

          <RailSection label="decisions">
            <DecisionCount decision="driver" count={decisionCounts.driver} />
            <DecisionCount decision="watch" count={decisionCounts.watch} />
            <DecisionCount decision="discard" count={decisionCounts.discard} />
          </RailSection>

          <RailSection label="watchlist">
            <div className="watchlist">
              {(statusQuery.data?.data.handles ?? bootstrapQuery.data?.data.handles ?? []).slice(0, 10).map((handle) => (
                <button type="button" key={handle} onClick={() => runSearch(`@${handle}`)}>
                  <span>{handle.slice(0, 1).toUpperCase()}</span>@{handle}
                </button>
              ))}
            </div>
          </RailSection>

          <div className="rail-footer">
            <span>kbd · 1-3 windows · / search</span>
          </div>
        </aside>

        <section className="center-column">
          {activeView === "signal_lab" ? (
            <SignalLabWorkbench
              assetFilter={signalLabAsset}
              data={signalLabData}
              handleFilter={signalLabHandle}
              horizon={signalLabHorizon}
              isLoading={signalLabChainsQuery.isPending}
              isFetchingNextPage={signalLabChainsQuery.isFetchingNextPage}
              hasNextPage={Boolean(signalLabChainsQuery.hasNextPage)}
              searchFilter={signalLabSearch}
              selectedChainId={selectedSignalChainId}
              stageFilter={signalLabStage}
              onAssetChange={setSignalLabAsset}
              onHandleChange={setSignalLabHandle}
              onHorizonChange={setSignalLabHorizon}
              onLoadMore={() => void signalLabChainsQuery.fetchNextPage()}
              onSearchChange={setSignalLabSearch}
              onSelect={selectSignalChain}
              onStageChange={setSignalLabStage}
            />
          ) : (
            <>
              <div className="radar-control-row">
                <div className="segmented">
                  {WINDOWS.map((item) => (
                    <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
                      {item}
                    </button>
                  ))}
                </div>
                <div className="segmented scope-toggle" aria-label="token flow scope">
                  <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">
                    watched
                  </button>
                  <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
                    all
                  </button>
                </div>
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

              <div className="bottom-deck">
                <LiveSignalTape
                  isLoading={recentQuery.isPending}
                  items={liveSignalTapeItems}
                  selectedEventId={selectedTapeEventId}
                  socketStatus={socket.status}
                  onSelect={handleTapeSelect}
                />

                <SignalLabPulse
                  data={signalLabData}
                  isLoading={signalLabChainsQuery.isPending}
                  selectedChainId={selectedSignalChainId}
                  onOpenLab={() => {
                    setActiveView("signal_lab");
                    setMobileTask("lab");
                  }}
                  onSelect={selectSignalChain}
                />
              </div>
            </>
          )}
        </section>

        {mobileTask === "tape" || mobileTask === "lab" ? null : selectedSignalChain ? (
          <SignalLabInspector
            activeTab={signalLabInspectorTab}
            chain={selectedSignalChain}
            onTabChange={setSignalLabInspectorTab}
          />
        ) : selectedEvidenceDetails ? (
          <EvidenceDetailDrawer {...selectedEvidenceDetails} />
        ) : (
          <TokenDetailDrawer
            accountQuality={accountQualityQuery.data?.data}
            activeTab={detailTab}
            hideDuplicateClusters={hideDuplicateClusters}
            isAccountQualityLoading={accountQualityQuery.isFetching}
            isSignalLabLoading={signalLabChainsQuery.isFetching}
            isPostsFetchingNextPage={tokenPostsQuery.isFetchingNextPage}
            isPostsLoading={tokenPostsQuery.isLoading}
            isTimelineLoading={tokenTimelineQuery.isFetching}
            postSortMode={postSortMode}
            posts={tokenPostsData}
            signalChains={selectedTokenSignalChains}
            timeline={tokenTimelineQuery.data?.data}
            timelineBucket={timelineBucket}
            token={selectedToken}
            watchedPostsOnly={watchedPostsOnly}
            onHideDuplicateClustersChange={setHideDuplicateClusters}
            onLoadMorePosts={() => void tokenPostsQuery.fetchNextPage()}
            onPostSortModeChange={setPostSortMode}
            onSelectSignalChain={selectSignalChain}
            onTabChange={setDetailTab}
            onTimelineBucketChange={setTimelineBucket}
            onWatchedPostsOnlyChange={setWatchedPostsOnly}
          />
        )}
      </div>
      {selectedSignal ? (
        <MobileTaskNav
          activeTask={mobileTask}
          detailAvailable={Boolean(selectedSignal || selectedToken)}
          onTaskChange={setMobileTask}
        />
      ) : null}
    </main>
  );
}

function RailSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="rail-section">
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

function CompactPanel({ title, icon, action, children }: { title: string; icon: ReactNode; action?: string; children: ReactNode }) {
  return (
    <section className="compact-panel">
      <header>
        <div>
          {icon}
          <h2>{title}</h2>
        </div>
        {action ? <span>{action}</span> : null}
      </header>
      {children}
    </section>
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

function latestSignalChainForSelection(selected: SignalLabChain, items: SignalLabChain[]): SignalLabChain {
  return items.find((item) => item.chain_id === selected.chain_id) ?? selected;
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

function mergeSignalLabPages(pages?: SignalLabChainsData[]): SignalLabChainsData | undefined {
  if (!pages?.length) {
    return undefined;
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

function jobSummary(counts?: Record<string, number>): string {
  if (!counts) {
    return "-";
  }
  return `p${counts.pending ?? 0}/r${counts.running ?? 0}/f${counts.failed ?? 0}/d${counts.dead ?? 0}`;
}

function defaultSignalLabHealth(status?: StatusData): HarnessHealth {
  return {
    llm_configured: Boolean(status?.enrichment.llm_configured),
    extractor_running: Boolean(status?.enrichment.worker_running),
    schema_success_rate: null,
    pending_jobs: status?.enrichment.job_counts.pending ?? 0,
    snapshots_24h: 0,
    pending_outcomes: 0,
    settlement_coverage: null
  };
}

function formatSignalLabCoverage(value?: number | null): string {
  return value === null || value === undefined ? "-" : `${Math.round(value * 100)}%`;
}

function selectedSignalChainIdForSelection(signal: SelectedSignal): string | null {
  if (signal?.kind === "signal_chain") return signal.item.chain_id;
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

function filterSignalChainsForToken(token: TokenFlowItem | null, chains: SignalLabChain[]): SignalLabChain[] {
  if (!token) {
    return [];
  }
  const identities = new Set([token.identity.symbol?.toUpperCase(), token.identity.address?.toUpperCase(), token.identity.token_id?.toUpperCase()].filter(Boolean));
  return chains.filter((chain) => {
    const asset = chain.asset?.toUpperCase();
    return asset ? identities.has(asset) : false;
  });
}

function preferredSignalChain(chains: SignalLabChain[]): SignalLabChain {
  return [...chains].sort((a, b) => signalChainStageRank(b) - signalChainStageRank(a) || b.updated_at_ms - a.updated_at_ms)[0];
}

function signalChainStageRank(chain: SignalLabChain): number {
  if (chain.stage === "credited") return 5;
  if (chain.stage === "settled") return 4;
  if (chain.stage === "frozen") return 3;
  if (chain.stage === "seeded") return 2;
  return 1;
}
