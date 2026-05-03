import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Brain,
  Clock3,
  Database,
  ExternalLink,
  Flame,
  Hash,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  UserRound,
  Wifi,
  Zap
} from "lucide-react";
import { getApi, getBootstrap } from "./api/client";
import type {
  AccountAlertsData,
  AlertRecord,
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
import { compactNumber, eventHandle, eventText, formatPercentShare, formatRelativeTime, tokenLabel } from "./lib/format";
import { useTraderStore } from "./store/useTraderStore";

const WINDOWS: WindowKey[] = ["1m", "5m", "1h", "24h"];
const ACCOUNT_ALERT_WINDOW: WindowKey = "24h";

type SelectedSignal =
  | { kind: "token"; item: TokenFlowItem }
  | { kind: "alert"; item: AlertRecord }
  | { kind: "event"; item: LivePayload }
  | { kind: "search"; item: SearchItem }
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
  const setToken = useTraderStore((state) => state.setToken);
  const setWindow = useTraderStore((state) => state.setWindow);
  const setScope = useTraderStore((state) => state.setScope);
  const setHandles = useTraderStore((state) => state.setHandles);
  const setSearch = useTraderStore((state) => state.setSearch);
  const submitSearch = useTraderStore((state) => state.submitSearch);
  const runSearch = useTraderStore((state) => state.runSearch);
  const [selectedSignal, setSelectedSignal] = useState<SelectedSignal>(null);

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
    queryKey: ["token-flow", windowKey],
    queryFn: () => getApi<TokenFlowData>("/api/token-flow", { token, params: { window: windowKey, limit: 48 } }),
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
  const focus = buildEvidenceFocus(selectedSignal, searchItems, submittedSearch);

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

  return (
    <main className="cockpit-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">GI</div>
          <div>
            <h1>GMGN Twitter Intel</h1>
            <p>交易员实时情报台 · signal to evidence</p>
          </div>
        </div>

        <form
          className="searchbar"
          onSubmit={(event) => {
            event.preventDefault();
            submitEvidenceSearch();
          }}
        >
          <Search aria-hidden />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 CA / $TOKEN / @handle / 文本" />
          <button type="submit">检索</button>
        </form>

        <div className="top-actions">
          <button className="icon-button" type="button" onClick={handleRefresh} title="刷新">
            <RefreshCw aria-hidden />
          </button>
        </div>
      </header>

      <section className="control-strip">
        <div className="segmented">
          {WINDOWS.map((item) => (
            <button key={item} className={item === windowKey ? "active" : ""} onClick={() => setWindow(item)} type="button">
              {item}
            </button>
          ))}
        </div>
        <div className="segmented compact">
          <button className={scope === "matched" ? "active" : ""} onClick={() => setScope("matched")} type="button">
            watched
          </button>
          <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")} type="button">
            all
          </button>
        </div>
        <div className="handle-filter">
          <UserRound aria-hidden />
          <input value={handles} onChange={(event) => setHandles(event.target.value)} placeholder="handles: toly,elonmusk" />
        </div>
        <StatusPills
          socketStatus={socket.status}
          configReady={Boolean(token)}
          status={statusQuery.data?.data}
          lastMessageAt={socket.lastMessageAt}
        />
      </section>

      <section className="metrics-row">
        <Metric icon={<Radio />} label="LIVE" value={socket.status} tone={socket.status === "connected" ? "green" : "amber"} />
        <Metric icon={<Activity />} label="FRAMES" value={compactNumber(statusQuery.data?.data.collector.frames_received)} />
        <Metric icon={<Zap />} label="MATCHED" value={compactNumber(statusQuery.data?.data.collector.matched_twitter_events)} />
        <Metric icon={<Brain />} label="LLM JOBS" value={jobSummary(enrichmentJobsQuery.data?.data.counts)} />
        <Metric icon={<Database />} label="STORE" value={shortPath(statusQuery.data?.data.store)} wide />
      </section>

      <section className="grid-main">
        <Panel title="实时信号 Tape" icon={<Flame />} action={`${liveItems.length} 条`} subtitle="按时间倒序，看账号、实体、告警和原文证据">
          <div className="event-list">
            {liveItems.length ? (
              liveItems.slice(0, 30).map((item) => (
                <EventRow key={item.event.event_id} payload={item} selected={isSelectedEvent(selectedSignal, item)} onSelect={selectEvent} />
              ))
            ) : (
              <EmptyState text={token ? "等待 replay 或 live event" : "读取运行配置中"} />
            )}
          </div>
        </Panel>

        <Panel title="Token Flow" icon={<Hash />} action={windowKey} subtitle="点击 token 直接检索证据链">
          <div className="dense-table">
            <div className="table-head token-grid">
              <span>Token</span>
              <span>提及</span>
              <span>份额</span>
              <span>速度</span>
            </div>
            {tokenItems.slice(0, 24).map((item) => (
              <TokenRow key={`${item.entity_key}:${item.window_start_ms ?? ""}`} item={item} selected={isSelectedToken(selectedSignal, item)} onSelect={selectToken} />
            ))}
            {tokenItems.length === 0 ? <EmptyState text="暂无 token flow" /> : null}
          </div>
        </Panel>

        <Panel title="焦点证据" icon={<ShieldCheck />} action={focus.badge} subtitle="选中任意信号后，看证据、来源和风险">
          <EvidenceFocus focus={focus} />
        </Panel>

        <Panel title="关注账号告警" icon={<AlertTriangle />} action={ACCOUNT_ALERT_WINDOW} subtitle="watched account 提到 token/CA 的事件">
          <div className="alert-list">
            {alertItems.slice(0, 24).map((item) => (
              <AlertRow key={`${item.alert_type}:${item.event_id}:${item.entity_key ?? item.narrative_label ?? ""}`} item={item} selected={isSelectedAlert(selectedSignal, item)} onSelect={selectAlert} />
            ))}
            {alertItems.length === 0 ? <EmptyState text="24h 内暂无 watched-account token 告警" /> : null}
          </div>
        </Panel>

        <Panel title="证据检索" icon={<Search />} action={`${searchQuery.data?.data.result_count ?? 0} hits`} subtitle="exact CA / symbol / handle / FTS">
          <div className="search-results">
            {searchItems.slice(0, 24).map((item) => (
              <SearchRow key={`${item.match_type}:${item.event.event_id}`} item={item} selected={isSelectedSearch(selectedSignal, item)} onSelect={selectSearchItem} />
            ))}
            {searchQuery.isFetching ? <EmptyState text="检索中" /> : null}
            {!searchQuery.isFetching && searchItems.length === 0 ? <EmptyState text="输入 CA、$TOKEN、@handle 或关键词检索" /> : null}
          </div>
        </Panel>

        <Panel title="叙事流" icon={<Brain />} action={statusQuery.data?.data.enrichment.llm_configured ? "LLM on" : "LLM off"} subtitle="LLM 叙事必须回到 evidence">
          <div className="narrative-list">
            {(narrativeQuery.data?.data.items ?? []).slice(0, 16).map((item) => (
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
        </Panel>
      </section>
    </main>
  );
}

function StatusPills({
  socketStatus,
  configReady,
  status,
  lastMessageAt
}: {
  socketStatus: string;
  configReady: boolean;
  status?: StatusData;
  lastMessageAt: number | null;
}) {
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
      <span className={status?.ok ? "pill good" : "pill warn"}>
        <Activity aria-hidden />
        {status?.ok ? "ready" : "not ready"}
      </span>
      <span className="pill muted">
        <Clock3 aria-hidden />
        {lastMessageAt ? `${formatRelativeTime(lastMessageAt)} ago` : "no msg"}
      </span>
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
  tone,
  wide
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "green" | "amber";
  wide?: boolean;
}) {
  return (
    <div className={`metric ${tone ?? ""} ${wide ? "wide" : ""}`}>
      <span>{icon}</span>
      <div>
        <label>{label}</label>
        <strong>{value || "-"}</strong>
      </div>
    </div>
  );
}

function Panel({
  title,
  icon,
  action,
  subtitle,
  children
}: {
  title: string;
  icon: ReactNode;
  action?: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header>
        <div>
          {icon}
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {action ? <span>{action}</span> : null}
      </header>
      {children}
    </section>
  );
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

function TokenRow({
  item,
  selected,
  onSelect
}: {
  item: TokenFlowItem;
  selected: boolean;
  onSelect: (item: TokenFlowItem) => void;
}) {
  return (
    <button
      aria-label={`select token ${tokenLabel(item)}`}
      className={`table-row token-grid ${selected ? "is-selected" : ""}`}
      type="button"
      onClick={() => onSelect(item)}
    >
      <strong>{tokenLabel(item)}</strong>
      <span>{compactNumber(item.watched_mention_count)} / {compactNumber(item.mention_count)}</span>
      <span>{formatPercentShare(item.market_mindshare)}</span>
      <b>{compactNumber(item.velocity ?? 0)}</b>
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

function EvidenceFocus({ focus }: { focus: EvidenceFocusModel }) {
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
  evidence: Array<{ id: string; handle: string; match: string; receivedAt?: number | null; text: string; url?: string | null }>;
  authors: string[];
  risks: string[];
};

function buildEvidenceFocus(signal: SelectedSignal, searchItems: SearchItem[], submittedSearch: string): EvidenceFocusModel {
  if (signal?.kind === "token") {
    const item = signal.item;
    return {
      kicker: "token flow",
      title: tokenLabel(item),
      summary: `${formatPercentShare(item.market_mindshare)} market mindshare, ${compactNumber(item.watched_mention_count)} watched / ${compactNumber(item.mention_count)} total mentions across ${compactNumber(item.unique_author_count)} accounts.`,
      score: String(tokenScore(item)),
      badge: item.window,
      facts: [
        { label: "entity", value: item.entity_type },
        { label: "market share", value: formatPercentShare(item.market_mindshare) },
        { label: "watched share", value: formatPercentShare(item.watched_mindshare) },
        { label: "accounts", value: compactNumber(item.unique_author_count) },
        { label: "velocity", value: compactNumber(item.velocity ?? 0) }
      ],
      evidence: evidenceFromSearch(searchItems),
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
  return item.entity_type === "symbol" ? `$${item.normalized_value}` : item.normalized_value;
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
  return Math.min(
    99,
    Math.round(
      (item.watched_mention_count * 28) +
      (item.unique_author_count * 7) +
      ((item.velocity ?? 0) * 18) +
      (item.market_mindshare * 30) +
      (item.watched_mindshare * 40) +
      Math.log1p(item.mention_count) * 12
    )
  );
}

function tokenRisks(item: TokenFlowItem): string[] {
  const risks = ["coverage public_stream"];
  if (item.entity_type === "symbol") {
    risks.push("symbol-only until CA confirms");
  }
  if (!item.watched_mention_count) {
    risks.push("no watched-account confirmation");
  }
  return risks;
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
  return (item.top_authors ?? []).slice(0, 6).map((author) => `${author.handle ?? "unknown"} x${author.count ?? 1}`);
}

function isSelectedToken(signal: SelectedSignal, item: TokenFlowItem): boolean {
  return signal?.kind === "token" && signal.item.entity_key === item.entity_key && signal.item.window_start_ms === item.window_start_ms;
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

function shortId(value?: string): string {
  if (!value) {
    return "-";
  }
  return value.length > 16 ? value.slice(-12) : value;
}
