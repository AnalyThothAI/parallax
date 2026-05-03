import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  Clock3,
  ExternalLink,
  Flame,
  RefreshCw,
  Search,
  UserRound,
  Wifi,
  Zap
} from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import type {
  AccountAlertsData,
  AlertRecord,
  AttentionFrontierItem,
  AttentionFrontierData,
  EnrichmentJobsData,
  EventRecord,
  LivePayload,
  NarrativeFlowData,
  RecentData,
  SearchData,
  SearchItem,
  StatusData,
  TokenFlowData,
  TokenFlowItem,
  WindowKey
} from "./api/types";
import { useIntelSocket } from "./api/useIntelSocket";
import { compactNumber, eventHandle, eventText, formatPercentShare, formatRelativeTime, formatSignedPercent, formatUsdCompact, tokenLabel } from "./lib/format";
import { useTraderStore } from "./store/useTraderStore";

const WINDOWS: WindowKey[] = ["5m", "1h", "24h"];
const ACCOUNT_ALERT_WINDOW: WindowKey = "24h";

type SelectedSignal =
  | { kind: "token"; item: TokenFlowItem }
  | { kind: "alert"; item: AlertRecord }
  | { kind: "event"; item: LivePayload }
  | { kind: "search"; item: SearchItem }
  | { kind: "query"; query: string }
  | null;

type Decision = "driver" | "watch" | "discard";

export function App() {
  const queryClient = useQueryClient();
  const windowKey = useTraderStore((state) => state.window);
  const scope = useTraderStore((state) => state.scope);
  const handles = useTraderStore((state) => state.handles);
  const search = useTraderStore((state) => state.search);
  const submittedSearch = useTraderStore((state) => state.submittedSearch);
  const token = useTraderStore((state) => state.token);
  const setToken = useTraderStore((state) => state.setToken);
  const setWindow = useTraderStore((state) => state.setWindow);
  const setScope = useTraderStore((state) => state.setScope);
  const setHandles = useTraderStore((state) => state.setHandles);
  const setSearch = useTraderStore((state) => state.setSearch);
  const submitSearch = useTraderStore((state) => state.submitSearch);
  const runSearch = useTraderStore((state) => state.runSearch);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
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
    queryFn: () => getApi<TokenFlowData>("/api/token-flow", { token, params: { window: windowKey, limit: 48, scope } }),
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
  const narrativeQuery = useQuery({
    queryKey: ["narrative-flow", windowKey],
    queryFn: () =>
      getApi<NarrativeFlowData>("/api/narrative-flow", {
        token,
        params: { window: windowKey, limit: 30 }
      }),
    enabled: Boolean(token),
    refetchInterval: 18_000
  });
  const frontierQuery = useQuery({
    queryKey: ["attention-frontier", windowKey],
    queryFn: () =>
      getApi<AttentionFrontierData>("/api/attention-frontier", {
        token,
        params: { window: windowKey, limit: 20 }
      }),
    enabled: Boolean(token),
    refetchInterval: 18_000
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

  const liveItems = useMemo(() => {
    const replayItems = recentQuery.data?.data.items ?? [];
    const byId = new Map<string, LivePayload>();
    for (const item of [...socket.events, ...replayItems]) {
      byId.set(item.event.event_id, item);
    }
    return [...byId.values()].sort((a, b) => Number(b.event.received_at_ms ?? 0) - Number(a.event.received_at_ms ?? 0));
  }, [recentQuery.data?.data.items, socket.events]);

  const tokenItems = tokenFlowQuery.data?.data.items ?? [];
  const alertItems = alertsQuery.data?.data.items ?? [];
  const searchItems = searchQuery.data?.data.items ?? [];
  const frontierItems = frontierQuery.data?.data.items ?? [];
  const frontierByToken = useMemo(() => buildFrontierByToken(frontierItems), [frontierItems]);
  const focus = buildEvidenceFocus(selectedSignal, searchItems, submittedSearch);
  const selectedToken = selectedSignal?.kind === "token" ? selectedSignal.item : null;
  const selectedTokenKey = selectedToken ? tokenDecisionKey(selectedToken) : null;
  const selectedDecision = selectedToken ? decisionForToken(selectedToken, decisions) : null;
  const decisionCounts = useMemo(() => countDecisions(tokenItems, decisions), [tokenItems, decisions]);

  useEffect(() => {
    if (!selectedSignal && tokenItems.length) {
      setSelectedSignal({ kind: "token", item: tokenItems[0] });
    }
  }, [selectedSignal, tokenItems]);

  const selectToken = (item: TokenFlowItem) => {
    setSelectedSignal({ kind: "token", item });
    runSearch(tokenSearchQuery(item));
  };

  const selectAlert = (item: AlertRecord) => {
    setSelectedSignal({ kind: "alert", item });
    runSearch(alertSearchQuery(item));
  };

  const selectSearchItem = (item: SearchItem) => {
    setSelectedSignal({ kind: "search", item });
  };

  const selectEvent = (item: LivePayload) => {
    setSelectedSignal({ kind: "event", item });
  };

  const submitEvidenceSearch = () => {
    const query = search.trim();
    submitSearch();
    setSelectedSignal(query ? { kind: "query", query } : null);
  };

  const handleRefresh = () => {
    void queryClient.invalidateQueries();
  };

  const setTokenDecision = (decision: Decision) => {
    if (!selectedTokenKey) {
      return;
    }
    setDecisions((current) => ({ ...current, [selectedTokenKey]: decision }));
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
    if (event.key.toLowerCase() === "d") setTokenDecision("driver");
    if (event.key.toLowerCase() === "w") setTokenDecision("watch");
    if (event.key.toLowerCase() === "x") setTokenDecision("discard");
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
          socketStatus={socket.status}
          configReady={Boolean(token)}
          status={statusQuery.data?.data}
          statusLoading={Boolean(token) && statusQuery.isPending}
          statusError={statusQuery.isError}
          lastMessageAt={socket.lastMessageAt}
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
          <span>MATCHED <b>{compactNumber(statusQuery.data?.data.collector.matched_twitter_events)}</b></span>
          <span>flow·{windowKey} <b>{compactNumber(liveItems.length)}</b></span>
          <span>enrich <b>{jobSummary(enrichmentJobsQuery.data?.data.counts)}</b></span>
        </div>

        <button className="icon-button" type="button" onClick={handleRefresh} title="刷新" aria-label="刷新">
          <RefreshCw aria-hidden />
        </button>
      </header>

      <div className="cockpit-grid">
        <aside className="side-rail">
          <RailSection label="views">
            <RailButton active label="Live" value={liveItems.length} index="1" />
            <RailButton active label="Tokens" value={tokenItems.length} index="2" />
            <RailButton label="Narratives" value={narrativeQuery.data?.data.items.length ?? 0} index="3" />
            <RailButton label="Accounts" value={statusQuery.data?.data.handles.length ?? 0} index="4" />
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
              <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">watched</button>
              <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">all stream</button>
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
            <span>D / W / X tag selected</span>
          </div>
        </aside>

        <section className="radar-panel" aria-label="Token Flow">
          <header className="radar-toolbar">
            <div>
              <h2>Token Flow</h2>
              <span>TOKEN RADAR <b>{tokenItems.length}</b></span>
            </div>
            <div className="toolbar-controls">
              <div className="segmented">
                {WINDOWS.map((item) => (
                  <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
                    {item}
                  </button>
                ))}
              </div>
              <button className="filter-chip" type="button" onClick={() => setScope(scope === "matched" ? "all" : "matched")}>
                {scope === "matched" ? "watched" : "all"}
              </button>
            </div>
          </header>

          <div className="token-radar-table">
            <div className="radar-head">
              <span />
              <span>Token</span>
              <span>MCap</span>
              <span>Δ</span>
              <span>Flow</span>
              <span>Sources</span>
              <span>Fresh</span>
              <span>Signal</span>
            </div>
	            {tokenItems.slice(0, 40).map((item) => (
	              <TokenRadarRow
	                key={`${item.identity.identity_key}:${item.flow.window_start_ms ?? ""}`}
	                item={item}
	                decision={decisionForToken(item, decisions)}
	                narrativeLink={frontierMatchForToken(item, frontierByToken)}
	                selected={isSelectedToken(selectedSignal, item)}
	                onSelect={selectToken}
	              />
	            ))}
            {tokenItems.length === 0 ? <EmptyState text="暂无 token flow" /> : null}
          </div>

          <div className="bottom-deck">
            <CompactPanel title="实时信号 Tape" icon={<Flame />} action={`${liveItems.length} 条`}>
              <div className="compact-list">
                {liveItems.length ? (
                  liveItems.slice(0, 8).map((item) => (
                    <EventRow key={item.event.event_id} payload={item} selected={isSelectedEvent(selectedSignal, item)} onSelect={selectEvent} />
                  ))
                ) : (
                  <EmptyState text={token ? "等待 replay 或 live event" : "读取运行配置中"} />
                )}
              </div>
            </CompactPanel>

            <CompactPanel title="关注账号告警" icon={<AlertTriangle />} action={ACCOUNT_ALERT_WINDOW}>
              <div className="compact-list">
                {alertItems.slice(0, 8).map((item) => (
                  <AlertRow key={`${item.alert_type}:${item.event_id}:${item.entity_key ?? item.narrative_label ?? ""}`} item={item} selected={isSelectedAlert(selectedSignal, item)} onSelect={selectAlert} />
                ))}
                {alertItems.length === 0 ? <EmptyState text="24h 内暂无 watched-account token 告警" /> : null}
              </div>
            </CompactPanel>

            <CompactPanel title="检索结果" icon={<Search />} action={`${searchQuery.data?.data.result_count ?? 0} hits`}>
              <div className="compact-list">
                {searchItems.slice(0, 8).map((item) => (
                  <SearchRow key={`${item.match_type}:${item.event.event_id}`} item={item} selected={isSelectedSearch(selectedSignal, item)} onSelect={selectSearchItem} />
                ))}
                {searchQuery.isFetching ? <EmptyState text="检索中" /> : null}
                {!searchQuery.isFetching && searchItems.length === 0 ? <EmptyState text="输入 CA、$TOKEN、@handle 或关键词检索" /> : null}
              </div>
            </CompactPanel>
          </div>
        </section>

        <aside className="detail-drawer">
          <section className="detail-focus">
            <header className="drawer-head">
              <button type="button" aria-label="close detail">×</button>
              <div>
                <h2>焦点证据</h2>
                <span>{focus.badge}</span>
              </div>
            </header>
            <EvidenceFocus focus={focus} decision={selectedDecision} onDecision={setTokenDecision} />
          </section>
          <CompactPanel title="叙事前沿" icon={<Brain />} action={`${frontierQuery.data?.data.items.length ?? 0} links`}>
            <div className="narrative-list">
	              {frontierItems.slice(0, 8).map((item) => (
                <div className="narrative-row frontier-row" key={`${item.seed.seed_id}:${item.link.identity.identity_key}`}>
                  <div>
                    <strong>
                      @{item.seed.author_handle ?? "watched"} <ArrowRight aria-hidden /> ${item.link.identity.symbol ?? "TOKEN"}
                    </strong>
                    <span>{item.seed.narrative_label} · {item.link.evidence.link_reason ?? "linked evidence"}</span>
                  </div>
                  <DecisionTag decision={item.link.signal.decision} />
                </div>
              ))}
	              {frontierItems.length === 0 ? <EmptyState text="暂无 seed-token link" /> : null}
            </div>
          </CompactPanel>
          <CompactPanel title="叙事流" icon={<Brain />} action={statusQuery.data?.data.enrichment.llm_configured ? "LLM on" : "LLM off"}>
            <div className="narrative-list">
              {(narrativeQuery.data?.data.items ?? []).slice(0, 8).map((item) => (
                <div className="narrative-row" key={`${item.narrative_label}:${item.window}`}>
                  <div>
                    <strong>{item.narrative_label}</strong>
                    <span>{compactNumber(item.watched_mention_count)} watched / {compactNumber(item.mention_count)} total</span>
                  </div>
                  <b>{compactNumber(item.velocity ?? 0)}</b>
                </div>
              ))}
              {narrativeQuery.data?.data.items.length === 0 ? <EmptyState text="LLM 叙事窗口暂无数据" /> : null}
            </div>
          </CompactPanel>
        </aside>
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
      <DecisionTag decision={decision} />
      <b>{compactNumber(count)}</b>
    </span>
  );
}

function DecisionTag({ decision }: { decision: Decision }) {
  return <span className={`decision-tag ${decision}`}>{decision}</span>;
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

function EventRow({
  payload,
  selected,
  onSelect
}: {
  payload: LivePayload;
  selected: boolean;
  onSelect: (payload: LivePayload) => void;
}) {
  const event = payload.event;
  const alerts = payload.alerts ?? [];
  const entities = payload.entities ?? [];
  return (
    <article className={`event-row ${selected ? "is-selected" : ""}`} onClick={() => onSelect(payload)} role="button" tabIndex={0}>
      <div className="event-meta">
        <b>@{eventHandle(event)}</b>
        <span>{formatRelativeTime(event.received_at_ms)}</span>
        {alerts.length ? <em>ALERT {alerts.length}</em> : null}
        {event.canonical_url ? (
          <a href={event.canonical_url} target="_blank" rel="noreferrer" aria-label="打开原文" onClick={(event) => event.stopPropagation()}>
            <ExternalLink aria-hidden />
          </a>
        ) : null}
      </div>
      <p>{eventText(event)}</p>
      <div className="entity-tags">
        {entities.slice(0, 5).map((entity) => (
          <span key={`${entity.entity_type}:${entity.normalized_value}:${entity.chain ?? ""}`}>
            {entity.entity_type === "symbol" ? "$" : ""}
            {entity.normalized_value}
          </span>
        ))}
      </div>
    </article>
  );
}

function TokenRadarRow({
  item,
  decision,
  narrativeLink,
  selected,
  onSelect
}: {
  item: TokenFlowItem;
  decision: Decision;
  narrativeLink?: AttentionFrontierItem;
  selected: boolean;
  onSelect: (item: TokenFlowItem) => void;
}) {
  const delta = marketDelta(item);
  const direction = delta === "-" ? "flat" : delta.startsWith("+") ? "up" : delta.startsWith("-") ? "down" : "flat";
  return (
    <button
      aria-label={`select token ${tokenLabel(item)}`}
      className={`radar-row ${selected ? "is-selected" : ""}`}
      type="button"
      onClick={() => onSelect(item)}
    >
      <span className="signal-dot" aria-hidden />
      <strong className="token-symbol">
        <span className="symbol-line">
          <span>{tokenLabel(item)}</span>
          {narrativeLink ? (
            <span
              className="narrative-link-badge"
              title={`Narrative link: ${narrativeLink.seed.narrative_label}`}
              aria-label={`narrative link ${narrativeLink.seed.narrative_label}`}
            >
              <Brain aria-hidden />
            </span>
          ) : null}
        </span>
        <small>{tokenIdentityMeta(item)}</small>
      </strong>
      <span className={`mono ${item.market.market_cap ? "" : "muted"}`}>{formatUsdCompact(item.market.market_cap)}</span>
      <b className={`direction ${direction}`}>{delta}</b>
      <span className="flow-cell">
        <b>{compactNumber(item.flow.mentions)}</b>
        <small>{flowDeltaLabel(item)}</small>
      </span>
      <span className="source-cell">
        <b>{sourceCountLabel(item)}</b>
        <small>{sourceQualityLabel(item)}</small>
      </span>
      <span className="fresh-cell">
        <b>{formatDuration(item.fresh.latest_evidence_age_ms)}</b>
        <small>{item.market.market_status}</small>
      </span>
      <DecisionTag decision={decision} />
    </button>
  );
}

function AlertRow({
  item,
  selected,
  onSelect
}: {
  item: AlertRecord;
  selected: boolean;
  onSelect: (item: AlertRecord) => void;
}) {
  return (
    <button className={`alert-row ${selected ? "is-selected" : ""}`} type="button" onClick={() => onSelect(item)}>
      <div>
        <strong>@{item.author_handle ?? "unknown"}{" -> "}{alertTokenLabel(item)}</strong>
        <span>{alertReason(item)}</span>
      </div>
      <time>{formatRelativeTime(item.received_at_ms)}</time>
    </button>
  );
}

function SearchRow({
  item,
  selected,
  onSelect
}: {
  item: SearchItem;
  selected: boolean;
  onSelect: (item: SearchItem) => void;
}) {
  return (
    <button className={`search-row ${selected ? "is-selected" : ""}`} type="button" onClick={() => onSelect(item)}>
      <div>
        <strong>@{eventHandle(item.event)}</strong>
        <span>{item.match_type}</span>
        <time>{formatRelativeTime(item.event.received_at_ms)}</time>
      </div>
      <p>{eventText(item.event)}</p>
    </button>
  );
}

function EvidenceFocus({
  focus,
  decision,
  onDecision
}: {
  focus: EvidenceFocusModel;
  decision: Decision | null;
  onDecision: (decision: Decision) => void;
}) {
  return (
    <div className="focus-panel">
      <div className="focus-hero">
        <div>
          <span>{focus.kicker}</span>
          <strong>{focus.title}</strong>
          <p>{focus.summary}</p>
        </div>
        <b>{focus.score}</b>
      </div>
      <div className="decision-controls" aria-label="token decision">
        {(["driver", "watch", "discard"] as Decision[]).map((item) => (
          <button key={item} className={decision === item ? "active" : ""} type="button" onClick={() => onDecision(item)} disabled={!decision}>
            {item === "driver" ? "D" : item === "watch" ? "W" : "X"} · {item}
          </button>
        ))}
      </div>
      <div className="focus-kv">
        {focus.facts.map((fact) => (
          <div key={fact.label}>
            <span>{fact.label}</span>
            <b>{fact.value}</b>
          </div>
        ))}
      </div>
      <div className="focus-section">
        <h3>证据</h3>
        {focus.evidence.length ? (
          focus.evidence.map((item) => (
            <article className="focus-evidence" key={item.id}>
              <div>
                <strong>@{item.handle}</strong>
                <span>{item.match}</span>
                {item.score !== undefined ? <span>{compactNumber(item.score)}</span> : null}
                <time>{formatRelativeTime(item.receivedAt)}</time>
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" aria-label="打开原文">
                    <ExternalLink aria-hidden />
                  </a>
                ) : null}
              </div>
              <p>{item.text}</p>
            </article>
          ))
        ) : (
          <EmptyState text="选中 token、告警、检索结果或实时事件后查看证据" />
        )}
      </div>
      {focus.authors.length ? (
        <div className="focus-section">
          <h3>来源</h3>
          <div className="author-strip">
            {focus.authors.map((author) => (
              <span key={author}>{author}</span>
            ))}
          </div>
        </div>
      ) : null}
      {focus.risks.length ? (
        <div className="focus-section">
          <h3>风险</h3>
          <div className="risk-strip">
            {focus.risks.map((risk) => (
              <span key={risk}>{risk}</span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

type EvidenceFocusModel = {
  kicker: string;
  title: string;
  summary: string;
  score: string;
  badge: string;
  facts: Array<{ label: string; value: string }>;
  evidence: Array<{ id: string; handle: string; match: string; receivedAt?: number | null; text: string; url?: string | null; score?: number }>;
  authors: string[];
  risks: string[];
};

function buildEvidenceFocus(signal: SelectedSignal, searchItems: SearchItem[], submittedSearch: string): EvidenceFocusModel {
  if (signal?.kind === "token") {
    const item = signal.item;
    const baselineSignal = item.flow.z_score === null || item.flow.z_score === undefined ? item.flow.baseline_status : `z ${compactNumber(item.flow.z_score)}`;
    const marketSignal = item.market.market_status === "missing" ? "missing" : `${formatUsdCompact(item.market.market_cap)} ${marketDelta(item)}`;
    return {
      kicker: "token flow",
      title: tokenLabel(item),
      summary: `${compactNumber(item.flow.mentions)} mentions (${flowDeltaLabel(item)}), ${compactNumber(item.sources.watched_authors)}/${compactNumber(item.sources.unique_authors)} watched sources, market ${item.market.market_status}.`,
      score: String(tokenScore(item)),
      badge: item.flow.window,
      facts: [
        { label: "identity", value: item.identity.identity_status },
        { label: "address", value: shortAddress(item.identity.address ?? item.identity.identity_key) },
        { label: "mcap", value: formatUsdCompact(item.market.market_cap) },
        { label: "delta", value: marketDelta(item) },
        { label: "signal", value: item.signal.decision },
        { label: "source q", value: compactNumber(item.sources.source_quality_score) },
        { label: "baseline", value: baselineSignal },
        { label: "market", value: marketSignal },
        { label: "stream share", value: formatPercentShare(item.flow.stream_dominance) },
        { label: "fresh", value: formatDuration(item.fresh.latest_evidence_age_ms) }
      ],
      evidence: evidenceFromToken(item, searchItems),
      authors: authorsFromToken(item),
      risks: tokenRisks(item)
    };
  }
  if (signal?.kind === "alert") {
    const item = signal.item;
    return {
      kicker: item.alert_type,
      title: `${item.author_handle ?? "unknown"} -> ${alertTokenLabel(item)}`,
      summary: alertReason(item),
      score: item.is_first_seen_by_author ? "A1" : "A2",
      badge: ACCOUNT_ALERT_WINDOW,
      facts: [
        { label: "first global", value: yesNo(item.is_first_seen_global) },
        { label: "first author", value: yesNo(item.is_first_seen_by_author) },
        { label: "entity", value: item.entity_key ?? "-" },
        { label: "event", value: shortId(item.event_id) }
      ],
      evidence: evidenceFromSearch(searchItems),
      authors: item.author_handle ? [`${item.author_handle} x1`] : [],
      risks: alertRisks(item)
    };
  }
  if (signal?.kind === "event") {
    const payload = signal.item;
    return {
      kicker: payload.event.action ?? "event",
      title: `@${eventHandle(payload.event)}`,
      summary: eventText(payload.event) || "This event has no clean text payload.",
      score: payload.alerts.length ? "ALERT" : "EVT",
      badge: "event",
      facts: [
        { label: "entities", value: compactNumber(payload.entities.length) },
        { label: "alerts", value: compactNumber(payload.alerts.length) },
        { label: "coverage", value: payload.event.source?.coverage ?? "public_stream" },
        { label: "event", value: shortId(payload.event.event_id) }
      ],
      evidence: [evidenceFromEvent(payload.event, "selected_event")],
      authors: [`${eventHandle(payload.event)} x1`],
      risks: payload.event.is_watched ? ["watched source"] : ["public stream"]
    };
  }
  if (signal?.kind === "search") {
    const item = signal.item;
    return {
      kicker: item.match_type,
      title: `@${eventHandle(item.event)}`,
      summary: eventText(item.event),
      score: compactNumber(item.score),
      badge: submittedSearch || "query",
      facts: [
        { label: "match", value: item.match_type },
        { label: "score", value: compactNumber(item.score) },
        { label: "watched", value: yesNo(item.event.is_watched) },
        { label: "event", value: shortId(item.event.event_id) }
      ],
      evidence: [evidenceFromEvent(item.event, item.match_type)],
      authors: [`${eventHandle(item.event)} x1`],
      risks: item.match_type === "exact_symbol" ? ["symbol-only until CA confirms"] : []
    };
  }
  if (signal?.kind === "query") {
    return {
      kicker: "search query",
      title: signal.query,
      summary: `${compactNumber(searchItems.length)} evidence hits for ${signal.query}. Exact CA, symbol, and handle matches are ranked before FTS text.`,
      score: compactNumber(searchItems.length),
      badge: "search",
      facts: [
        { label: "query", value: signal.query },
        { label: "results", value: compactNumber(searchItems.length) },
        { label: "coverage", value: "public_stream" },
        { label: "mode", value: "evidence" }
      ],
      evidence: evidenceFromSearch(searchItems),
      authors: authorsFromSearch(searchItems),
      risks: searchRisks(signal.query, searchItems)
    };
  }
  return {
    kicker: "search",
    title: submittedSearch || "No signal selected",
    summary: submittedSearch ? `Showing evidence for ${submittedSearch}.` : "Select a token, alert, search result, or live event.",
    score: "-",
    badge: "focus",
    facts: [
      { label: "query", value: submittedSearch || "-" },
      { label: "results", value: compactNumber(searchItems.length) },
      { label: "coverage", value: "public_stream" },
      { label: "mode", value: "evidence" }
    ],
    evidence: evidenceFromSearch(searchItems),
    authors: [],
    risks: []
  };
}

function evidenceFromSearch(items: SearchItem[]) {
  return items.slice(0, 8).map((item) => evidenceFromEvent(item.event, item.match_type));
}

function evidenceFromToken(item: TokenFlowItem, searchItems: SearchItem[]) {
  const direct = item.evidence
    .filter((event) => event.event_id)
    .slice(0, 8)
    .map((event) => ({
      id: event.event_id ?? "-",
      handle: event.handle ?? "unknown",
      match: evidenceReasonLabel(event.reasons),
      receivedAt: event.received_at_ms,
      text: event.text ?? "",
      url: event.url,
      score: event.score
    }))
    .filter((event) => event.text || event.id !== "-");
  return direct.length ? direct : evidenceFromSearch(searchItems);
}

function authorsFromSearch(items: SearchItem[]): string[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const handle = eventHandle(item.event);
    counts.set(handle, (counts.get(handle) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([handle, count]) => `${handle} x${count}`);
}

function evidenceFromEvent(event: EventRecord, match: string) {
  return {
    id: event.event_id,
    handle: eventHandle(event),
    match,
    receivedAt: event.received_at_ms,
    text: eventText(event),
    url: event.canonical_url
  };
}

function tokenSearchQuery(item: TokenFlowItem): string {
  if (item.identity.address) {
    return item.identity.address;
  }
  return item.identity.symbol ? `$${item.identity.symbol}` : item.identity.identity_key;
}

function alertSearchQuery(item: AlertRecord): string {
  if (item.entity_key?.startsWith("symbol:") || item.normalized_value) {
    return item.normalized_value ? `$${item.normalized_value}` : `$${item.entity_key?.replace("symbol:", "") ?? ""}`;
  }
  return item.entity_key?.split(":").slice(-1)[0] ?? item.narrative_label ?? "";
}

function alertTokenLabel(item: AlertRecord): string {
  if (item.entity_key?.startsWith("symbol:") || (item.normalized_value && !item.chain)) {
    return `$${item.normalized_value ?? item.entity_key?.replace("symbol:", "")}`;
  }
  return item.normalized_value ?? item.narrative_label ?? item.entity_key ?? "-";
}

function alertReason(item: AlertRecord): string {
  if (item.is_first_seen_global) {
    return "first global evidence from watched account";
  }
  if (item.is_first_seen_by_author) {
    return "first time this watched account mentioned it";
  }
  return "repeat watched-account mention";
}

function tokenScore(item: TokenFlowItem): number {
  return item.signal.score;
}

function tokenRisks(item: TokenFlowItem): string[] {
  return item.signal.risks.length ? item.signal.risks : ["coverage_public_stream"];
}

function searchRisks(query: string, items: SearchItem[]): string[] {
  const risks = ["coverage public_stream"];
  if (/^\$/.test(query) || items.some((item) => item.match_type === "exact_symbol")) {
    risks.push("symbol-only until CA confirms");
  }
  if (items.length === 0) {
    risks.push("no local evidence match");
  }
  return risks;
}

function alertRisks(item: AlertRecord): string[] {
  const risks = ["coverage public_stream"];
  if (item.token_resolution_status === "unresolved_symbol" || item.entity_key?.startsWith("symbol:")) {
    risks.push("unresolved symbol");
  }
  return risks;
}

function authorsFromToken(item: TokenFlowItem): string[] {
  return (item.sources.top_authors ?? []).slice(0, 6).map((author) => `${author.handle ?? "unknown"} x${author.count ?? 1}`);
}

function tokenDecisionKey(item: TokenFlowItem): string {
  return item.identity.token_id ?? item.identity.address ?? item.identity.identity_key;
}

function buildFrontierByToken(items: AttentionFrontierItem[]): Map<string, AttentionFrontierItem> {
  const map = new Map<string, AttentionFrontierItem>();
  for (const item of items) {
    for (const key of frontierTokenKeys(item.link.identity)) {
      if (!map.has(key)) {
        map.set(key, item);
      }
    }
  }
  return map;
}

function frontierMatchForToken(item: TokenFlowItem, frontierByToken: Map<string, AttentionFrontierItem>): AttentionFrontierItem | undefined {
  for (const key of frontierTokenKeys(item.identity)) {
    const match = frontierByToken.get(key);
    if (match) {
      return match;
    }
  }
  return undefined;
}

function frontierTokenKeys(identity: {
  identity_key: string;
  token_id?: string | null;
  address?: string | null;
  symbol?: string | null;
}): string[] {
  return [
    `identity:${identity.identity_key}`,
    identity.token_id ? `token:${identity.token_id}` : "",
    identity.address ? `address:${identity.address.toLowerCase()}` : "",
    identity.symbol ? `symbol:${identity.symbol.toUpperCase()}` : ""
  ].filter(Boolean);
}

function decisionForToken(item: TokenFlowItem, decisions: Record<string, Decision>): Decision {
  const key = tokenDecisionKey(item);
  if (decisions[key]) {
    return decisions[key];
  }
  return item.signal.decision;
}

function countDecisions(items: TokenFlowItem[], decisions: Record<string, Decision>): Record<Decision, number> {
  return items.reduce<Record<Decision, number>>(
    (counts, item) => {
      counts[decisionForToken(item, decisions)] += 1;
      return counts;
    },
    { driver: 0, watch: 0, discard: 0 }
  );
}

function isSelectedToken(signal: SelectedSignal, item: TokenFlowItem): boolean {
  return signal?.kind === "token" && signal.item.identity.identity_key === item.identity.identity_key && signal.item.flow.window_start_ms === item.flow.window_start_ms;
}

function isSelectedAlert(signal: SelectedSignal, item: AlertRecord): boolean {
  return signal?.kind === "alert" && signal.item.event_id === item.event_id && signal.item.entity_key === item.entity_key;
}

function isSelectedEvent(signal: SelectedSignal, item: LivePayload): boolean {
  return signal?.kind === "event" && signal.item.event.event_id === item.event.event_id;
}

function isSelectedSearch(signal: SelectedSignal, item: SearchItem): boolean {
  return signal?.kind === "search" && signal.item.event.event_id === item.event.event_id && signal.item.match_type === item.match_type;
}

function yesNo(value: number | boolean | null | undefined): string {
  return value ? "yes" : "no";
}

function jobSummary(counts?: Record<string, number>): string {
  if (!counts) {
    return "-";
  }
  return `${counts.pending ?? 0}/${counts.running ?? 0}/${counts.failed ?? 0}`;
}

function shortPath(value?: string): string {
  if (!value) {
    return "-";
  }
  const parts = value.split("/");
  return parts.slice(-2).join("/");
}

function shortAddress(value?: string | null): string {
  if (!value) {
    return "-";
  }
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

function tokenIdentityMeta(item: TokenFlowItem): string {
  const chain = item.identity.chain ?? "unknown";
  return item.identity.identity_status === "resolved_ca" ? chain : `${chain} · ${item.identity.identity_status}`;
}

function flowDeltaLabel(item: TokenFlowItem): string {
  const delta = item.flow.mention_delta;
  if (delta > 0) {
    return `+${compactNumber(delta)}`;
  }
  if (delta < 0) {
    return `-${compactNumber(Math.abs(delta))}`;
  }
  return "flat";
}

function sourceQualityLabel(item: TokenFlowItem): string {
  return `${compactNumber(item.sources.watched_authors)} watch / qual ${compactNumber(item.sources.source_quality_score)}`;
}

function sourceCountLabel(item: TokenFlowItem): string {
  return `${compactNumber(item.sources.unique_authors)} src`;
}

function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return formatRelativeTime(Date.now() - value);
}

function evidenceReasonLabel(reasons: string[] | undefined): string {
  return reasons?.[0]?.replaceAll("_", " ") ?? "token evidence";
}

function marketDelta(item: TokenFlowItem): string {
  return formatSignedPercent(item.market.price_change_window_pct);
}

function shortId(value?: string): string {
  if (!value) {
    return "-";
  }
  return value.length > 16 ? value.slice(-12) : value;
}
