import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, RefreshCw, Search, ShieldCheck, UserRound, Wifi, Zap } from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import type {
  AccountAlertsData,
  AccountQualityData,
  AlertRecord,
  AttentionSeedItem,
  AttentionSeedsData,
  Decision,
  EnrichmentJobsData,
  HarnessCreditItem,
  HarnessCreditsData,
  HarnessHealth,
  HarnessHealthData,
  HarnessOutcomeItem,
  HarnessOutcomesData,
  HarnessSnapshotItem,
  HarnessSnapshotsData,
  LivePayload,
  RadarSortMode,
  RecentData,
  SearchData,
  SocialEventItem,
  SocialEventsData,
  StatusData,
  TokenFlowData,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey
} from "./api/types";
import { useIntelSocket } from "./api/useIntelSocket";
import { EvidenceDetailDrawer, type EvidenceDetailDrawerProps } from "./components/EvidenceDetailDrawer";
import { HarnessDetailDrawer } from "./components/HarnessDetailDrawer";
import { HarnessPanel } from "./components/HarnessPanel";
import { LiveSignalTape, type LiveSignalTapeItem, tokenTapeReason } from "./components/LiveSignalTape";
import { TokenDetailDrawer } from "./components/TokenDetailDrawer";
import { TokenRadarTable } from "./components/TokenRadarTable";
import {
  compactNumber,
  eventText,
  formatRelativeTime,
  tokenKey,
  tokenLabel
} from "./lib/format";
import { useTraderStore } from "./store/useTraderStore";

const WINDOWS: WindowKey[] = ["5m", "1h", "24h"];
const ACCOUNT_ALERT_WINDOW: WindowKey = "24h";

type SelectedSignal =
  | { kind: "token"; key: string; item: TokenFlowItem }
  | { kind: "event"; item: LivePayload }
  | { kind: "social_event"; item: SocialEventItem }
  | { kind: "attention_seed"; item: AttentionSeedItem }
  | { kind: "harness_snapshot"; item: HarnessSnapshotItem }
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
  const harnessView = useTraderStore((state) => state.harnessView);
  const harnessHorizon = useTraderStore((state) => state.harnessHorizon);
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
  const setHarnessView = useTraderStore((state) => state.setHarnessView);
  const setHarnessHorizon = useTraderStore((state) => state.setHarnessHorizon);
  const setTimelineBucket = useTraderStore((state) => state.setTimelineBucket);
  const setPostSortMode = useTraderStore((state) => state.setPostSortMode);
  const setHideDuplicateClusters = useTraderStore((state) => state.setHideDuplicateClusters);
  const setWatchedPostsOnly = useTraderStore((state) => state.setWatchedPostsOnly);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [selectedTapeEventId, setSelectedTapeEventId] = useState<string | null>(null);
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

  const socialEventsQuery = useQuery({
    queryKey: ["social-events", windowKey, handles],
    queryFn: () =>
      getApi<SocialEventsData>("/api/social-events", {
        token,
        params: { window: windowKey, limit: 50, handles }
      }),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const attentionSeedsQuery = useQuery({
    queryKey: ["attention-seeds", windowKey, handles],
    queryFn: () =>
      getApi<AttentionSeedsData>("/api/attention-seeds", {
        token,
        params: { window: windowKey, limit: 50, handles }
      }),
    enabled: Boolean(token),
    refetchInterval: 10_000
  });

  const harnessSnapshotsQuery = useQuery({
    queryKey: ["harness-snapshots", windowKey, harnessHorizon],
    queryFn: () =>
      getApi<HarnessSnapshotsData>("/api/harness-snapshots", {
        token,
        params: { window: windowKey, horizon: harnessHorizon, limit: 50 }
      }),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const harnessOutcomesQuery = useQuery({
    queryKey: ["harness-outcomes", windowKey, harnessHorizon],
    queryFn: () =>
      getApi<HarnessOutcomesData>("/api/harness-outcomes", {
        token,
        params: { window: windowKey, horizon: harnessHorizon, limit: 50 }
      }),
    enabled: Boolean(token),
    refetchInterval: 30_000
  });

  const harnessCreditsQuery = useQuery({
    queryKey: ["harness-credits", windowKey, harnessHorizon],
    queryFn: () =>
      getApi<HarnessCreditsData>("/api/harness-credits", {
        token,
        params: { window: windowKey, horizon: harnessHorizon, limit: 80 }
      }),
    enabled: Boolean(token),
    refetchInterval: 30_000
  });

  const harnessHealthQuery = useQuery({
    queryKey: ["harness-health"],
    queryFn: () => getApi<HarnessHealthData>("/api/harness-health", { token }),
    enabled: Boolean(token),
    refetchInterval: 15_000
  });

  const enrichmentJobsQuery = useQuery({
    queryKey: ["enrichment-jobs"],
    queryFn: () => getApi<EnrichmentJobsData>("/api/enrichment-jobs", { token, params: { limit: 20 } }),
    enabled: Boolean(token),
    refetchInterval: 18_000
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
  const socialEvents = socialEventsQuery.data?.data.items ?? [];
  const attentionSeeds = attentionSeedsQuery.data?.data.items ?? [];
  const harnessSnapshots = harnessSnapshotsQuery.data?.data.items ?? [];
  const harnessOutcomes = harnessOutcomesQuery.data?.data.items ?? [];
  const harnessCredits = harnessCreditsQuery.data?.data.items ?? [];
  const harnessHealth = harnessHealthQuery.data?.data ?? defaultHarnessHealth(statusQuery.data?.data);
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ attentionSeeds, harnessSnapshots, liveItems, socialEvents, tokenItems }),
    [attentionSeeds, harnessSnapshots, liveItems, socialEvents, tokenItems]
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const tokenPostsData = useMemo(() => mergePostPages(tokenPostsQuery.data?.pages), [tokenPostsQuery.data?.pages]);
  const selectedHarnessId = selectedHarnessObjectId(selectedSignal);
  const selectedHarnessDetails = useMemo(
    () => resolveHarnessDetails(selectedSignal, { attentionSeeds, harnessCredits, harnessOutcomes, harnessSnapshots, socialEvents }),
    [attentionSeeds, harnessCredits, harnessOutcomes, harnessSnapshots, selectedSignal, socialEvents]
  );
  const selectedEvidenceDetails = useMemo(
    () =>
      resolveEvidenceDetails(selectedSignal, {
        currentSearchData,
        searchError: searchQuery.error instanceof Error ? searchQuery.error : null,
        searchFetching: searchQuery.isFetching
      }),
    [currentSearchData, searchQuery.error, searchQuery.isFetching, selectedSignal]
  );
  const selectedTokenHarness = useMemo(
    () => filterHarnessForToken(selectedToken, { attentionSeeds, harnessCredits, harnessOutcomes, harnessSnapshots }),
    [attentionSeeds, harnessCredits, harnessOutcomes, harnessSnapshots, selectedToken]
  );

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

  const selectToken = (item: TokenFlowItem, tapeId: string | null = null) => {
    setSelectedSignal({ kind: "token", key: tokenKey(item), item });
    setDetailTab("timeline");
    setSelectedTapeEventId(tapeId);
  };

  const submitEvidenceSearch = () => {
    const query = search.trim();
    submitSearch();
    setSelectedSignal(query ? { kind: "query", query } : null);
    setSelectedTapeEventId(null);
  };

  const handleTapeSelect = (item: LiveSignalTapeItem) => {
    const id = tapeItemId(item);
    setSelectedTapeEventId(id);
    if (item.kind === "token") {
      selectToken(item.token, id);
      return;
    }
    if (item.kind === "social_event") {
      setSelectedSignal({ kind: "social_event", item: item.item });
      return;
    }
    if (item.kind === "attention_seed") {
      setSelectedSignal({ kind: "attention_seed", item: item.item });
      return;
    }
    if (item.kind === "harness_snapshot") {
      setSelectedSignal({ kind: "harness_snapshot", item: item.item });
      return;
    }
    setSelectedSignal({ kind: "event", item: item.payload });
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
            seeds <b>{compactNumber(attentionSeeds.length)}</b>
          </span>
          <span>
            snap <b>{compactNumber(harnessSnapshots.length)}</b>
          </span>
          <span>
            settled <b>{formatHarnessCoverage(harnessHealth.settlement_coverage)}</b>
          </span>
        </div>

        <button className="icon-button" type="button" onClick={() => void queryClient.invalidateQueries()} title="刷新" aria-label="刷新">
          <RefreshCw aria-hidden />
        </button>
      </header>

      <div className="cockpit-grid">
        <aside className="side-rail">
          <RailSection label="views">
            <RailButton active label="Live" value={liveItems.length} index="1" />
            <RailButton active label="Tokens" value={tokenItems.length} index="2" />
            <RailButton label="Signal Lab" value={harnessSnapshots.length || socialEvents.length} index="3" />
            <RailButton label="Accounts" value={accountQualityQuery.data?.data.accounts.length ?? 0} index="4" />
            <RailButton label="Jobs/Ops" value={enrichmentJobsQuery.data?.data.items.length ?? 0} index="5" />
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

            <section className="compact-panel">
              <header>
                <div>
                  <ShieldCheck aria-hidden />
                  <h2>Signal Lab</h2>
                </div>
                <span>{harnessHealth.llm_configured ? "social-event-v1" : "extractor off"}</span>
              </header>
              <HarnessPanel
                health={harnessHealth}
                horizon={harnessHorizon}
                isLoading={socialEventsQuery.isPending || attentionSeedsQuery.isPending || harnessSnapshotsQuery.isPending}
                seeds={attentionSeeds}
                selectedId={selectedHarnessId}
                snapshots={harnessSnapshots}
                socialEvents={socialEvents}
                view={harnessView}
                onSelectEvent={(item) => setSelectedSignal({ kind: "social_event", item })}
                onSelectSeed={(item) => setSelectedSignal({ kind: "attention_seed", item })}
                onSelectSnapshot={(item) => setSelectedSignal({ kind: "harness_snapshot", item })}
                onHorizonChange={setHarnessHorizon}
                onViewChange={setHarnessView}
              />
            </section>
          </div>
        </section>

        {selectedHarnessDetails ? (
          <HarnessDetailDrawer
            credits={selectedHarnessDetails.credits}
            outcome={selectedHarnessDetails.outcome}
            seed={selectedHarnessDetails.seed}
            snapshot={selectedHarnessDetails.snapshot}
            socialEvent={selectedHarnessDetails.socialEvent}
          />
        ) : selectedEvidenceDetails ? (
          <EvidenceDetailDrawer {...selectedEvidenceDetails} />
        ) : (
          <TokenDetailDrawer
            accountQuality={accountQualityQuery.data?.data}
            activeTab={detailTab}
            harnessCredits={selectedTokenHarness.credits}
            harnessOutcomes={selectedTokenHarness.outcomes}
            harnessSeeds={selectedTokenHarness.seeds}
            harnessSnapshots={selectedTokenHarness.snapshots}
            hideDuplicateClusters={hideDuplicateClusters}
            isAccountQualityLoading={accountQualityQuery.isFetching}
            isHarnessLoading={attentionSeedsQuery.isFetching || harnessSnapshotsQuery.isFetching || harnessOutcomesQuery.isFetching || harnessCreditsQuery.isFetching}
            isPostsFetchingNextPage={tokenPostsQuery.isFetchingNextPage}
            isPostsLoading={tokenPostsQuery.isLoading}
            isTimelineLoading={tokenTimelineQuery.isFetching}
            postSortMode={postSortMode}
            posts={tokenPostsData}
            timeline={tokenTimelineQuery.data?.data}
            timelineBucket={timelineBucket}
            token={selectedToken}
            watchedPostsOnly={watchedPostsOnly}
            onHideDuplicateClustersChange={setHideDuplicateClusters}
            onLoadMorePosts={() => void tokenPostsQuery.fetchNextPage()}
            onPostSortModeChange={setPostSortMode}
            onSelectSnapshot={(snapshot) => {
              setSelectedSignal({ kind: "harness_snapshot", item: snapshot });
              setSelectedTapeEventId(snapshot.snapshot_id);
            }}
            onTabChange={setDetailTab}
            onTimelineBucketChange={setTimelineBucket}
            onWatchedPostsOnlyChange={setWatchedPostsOnly}
          />
        )}
      </div>
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

function RailButton({ active, label, value, index }: { active?: boolean; label: string; value: number; index: string }) {
  return (
    <button className={`rail-button ${active ? "active" : ""}`} type="button">
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

function buildLiveSignalTapeItems({
  attentionSeeds,
  harnessSnapshots,
  liveItems,
  socialEvents,
  tokenItems
}: {
  attentionSeeds: AttentionSeedItem[];
  harnessSnapshots: HarnessSnapshotItem[];
  liveItems: LivePayload[];
  socialEvents: SocialEventItem[];
  tokenItems: TokenFlowItem[];
}): LiveSignalTapeItem[] {
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
    if (payload.harness?.social_event) {
      rows.push({
        kind: "social_event",
        item: payload.harness.social_event,
        score: payload.harness.social_event.confidence * 100,
        reason: payload.harness.social_event.event_type.replaceAll("_", " "),
        body: payload.harness.social_event.summary_zh || eventText(payload.event)
      });
    } else if (tokenMatch) {
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
  for (const item of socialEvents.slice(0, 8)) {
    rows.push({
      kind: "social_event",
      item,
      score: item.confidence * 100,
      reason: item.event_type.replaceAll("_", " "),
      body: item.summary_zh || item.subject
    });
  }
  for (const item of attentionSeeds.slice(0, 8)) {
    rows.push({
      kind: "attention_seed",
      item,
      score: item.token_uptake_count ? Math.min(100, item.token_uptake_count * 20) : null,
      reason: item.seed_status.replaceAll("_", " "),
      body: `${item.subject} · ${item.top_linked_symbols.join(", ") || "seed only"}`
    });
  }
  for (const item of harnessSnapshots.slice(0, 8)) {
    rows.push({
      kind: "harness_snapshot",
      item,
      score: item.combined_score * 100,
      reason: item.shadow_signal.replaceAll("_", " "),
      body: `${item.asset} · ${item.horizon} · ${item.outcome_status}`
    });
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
  if (item.kind === "social_event") {
    return item.item.extraction_id;
  }
  if (item.kind === "attention_seed") {
    return item.item.seed_id;
  }
  if (item.kind === "harness_snapshot") {
    return item.item.snapshot_id;
  }
  return item.payload.event.event_id;
}

function jobSummary(counts?: Record<string, number>): string {
  if (!counts) {
    return "-";
  }
  return `p${counts.pending ?? 0}/r${counts.running ?? 0}/f${counts.failed ?? 0}/d${counts.dead ?? 0}`;
}

function defaultHarnessHealth(status?: StatusData): HarnessHealth {
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

function formatHarnessCoverage(value?: number | null): string {
  return value === null || value === undefined ? "-" : `${Math.round(value * 100)}%`;
}

function selectedHarnessObjectId(signal: SelectedSignal): string | null {
  if (signal?.kind === "social_event") return signal.item.extraction_id;
  if (signal?.kind === "attention_seed") return signal.item.seed_id;
  if (signal?.kind === "harness_snapshot") return signal.item.snapshot_id;
  return null;
}

function resolveHarnessDetails(
  signal: SelectedSignal,
  data: {
    attentionSeeds: AttentionSeedItem[];
    harnessCredits: HarnessCreditItem[];
    harnessOutcomes: HarnessOutcomeItem[];
    harnessSnapshots: HarnessSnapshotItem[];
    socialEvents: SocialEventItem[];
  }
): { socialEvent: SocialEventItem | null; seed: AttentionSeedItem | null; snapshot: HarnessSnapshotItem | null; outcome: HarnessOutcomeItem | null; credits: HarnessCreditItem[] } | null {
  if (!signal || !["social_event", "attention_seed", "harness_snapshot"].includes(signal.kind)) {
    return null;
  }
  const socialEvent = signal.kind === "social_event" ? signal.item : data.socialEvents.find((item) => item.extraction_id === seedForSignal(signal, data.attentionSeeds)?.extraction_id) ?? null;
  const seed = seedForSignal(signal, data.attentionSeeds);
  const snapshot =
    signal.kind === "harness_snapshot"
      ? signal.item
      : data.harnessSnapshots.find((item) => seed?.top_linked_symbols.some((symbol) => symbol.toUpperCase() === item.asset.toUpperCase())) ?? null;
  const outcome = snapshot ? data.harnessOutcomes.find((item) => item.snapshot_id === snapshot.snapshot_id) ?? null : null;
  const credits = snapshot ? data.harnessCredits.filter((item) => item.snapshot_id === snapshot.snapshot_id) : [];
  return { socialEvent, seed, snapshot, outcome, credits };
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

function seedForSignal(signal: NonNullable<SelectedSignal>, seeds: AttentionSeedItem[]): AttentionSeedItem | null {
  if (signal.kind === "attention_seed") return signal.item;
  if (signal.kind === "social_event") return seeds.find((item) => item.extraction_id === signal.item.extraction_id) ?? null;
  if (signal.kind === "harness_snapshot") return seeds.find((item) => item.top_linked_symbols.some((symbol) => symbol.toUpperCase() === signal.item.asset.toUpperCase())) ?? null;
  return null;
}

function filterHarnessForToken(
  token: TokenFlowItem | null,
  data: {
    attentionSeeds: AttentionSeedItem[];
    harnessCredits: HarnessCreditItem[];
    harnessOutcomes: HarnessOutcomeItem[];
    harnessSnapshots: HarnessSnapshotItem[];
  }
): { seeds: AttentionSeedItem[]; snapshots: HarnessSnapshotItem[]; outcomes: HarnessOutcomeItem[]; credits: HarnessCreditItem[] } {
  if (!token) {
    return { seeds: [], snapshots: [], outcomes: [], credits: [] };
  }
  const symbols = new Set([token.identity.symbol?.toUpperCase(), token.identity.address?.toLowerCase(), token.identity.token_id?.toLowerCase()].filter(Boolean));
  const seeds = data.attentionSeeds.filter((seed) => seed.top_linked_symbols.some((symbol) => symbols.has(symbol.toUpperCase())));
  const snapshots = data.harnessSnapshots.filter((snapshot) => symbols.has(snapshot.asset.toUpperCase()));
  const snapshotIds = new Set(snapshots.map((snapshot) => snapshot.snapshot_id));
  const outcomes = data.harnessOutcomes.filter((outcome) => snapshotIds.has(outcome.snapshot_id));
  const credits = data.harnessCredits.filter((credit) => snapshotIds.has(credit.snapshot_id));
  return { seeds, snapshots, outcomes, credits };
}
