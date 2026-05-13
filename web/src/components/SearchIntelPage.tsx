import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type {
  ScopeKey,
  SearchAmbiguousResult,
  SearchInspectData,
  SearchTargetCandidate,
  SearchTopicResult,
  SearchTokenResult,
  WindowKey,
} from "../api/types";
import { useSearchInspectQuery } from "../api/useSearchInspectQuery";
import {
  parseSearchRouteState,
  serializeSearchRouteState,
  type SearchRouteState,
} from "../features/search/searchRouteState";
import {
  compactNumber,
  formatPercentShare,
  formatPropagationPhase,
  formatScore,
  formatTokenPriceUsd,
  formatUsdCompact,
  shortAddress,
} from "../lib/format";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchTimelinePanel } from "./SearchTimelinePanel";
import { SearchTwitterResults } from "./SearchTwitterResults";

const WINDOW_OPTIONS: WindowKey[] = ["5m", "1h", "4h", "24h"];
const SCOPE_OPTIONS: ScopeKey[] = ["all", "matched"];

export function SearchIntelPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const routeState = parseSearchRouteState(searchParams);
  const query = useSearchInspectQuery(routeState);
  const data = query.data?.data ?? null;

  const updateRoute = (patch: Partial<SearchRouteState>) => {
    const next = serializeSearchRouteState({ ...routeState, ...patch });
    navigate({ pathname: "/search", search: `?${next.toString()}` });
  };

  return (
    <section className="search-intel-page" aria-label="Search Intel">
      <SearchTopBar data={data} routeState={routeState} />

      {!routeState.q ? (
        <div className="search-empty-state">输入 token、CA、@handle 或关键词后手动检索。</div>
      ) : query.error ? (
        <div className="search-empty-state error">
          <b>Search Intel 请求失败</b>
          <span>{query.error instanceof Error ? query.error.message : "unknown error"}</span>
        </div>
      ) : query.isPending || !data ? (
        <div className="search-empty-state">loading search intel</div>
      ) : (
        <div className="search-workspace">
          <SearchIntelSidebar data={data} routeState={routeState} onRouteChange={updateRoute} />
          <SearchResultBody data={data} />
        </div>
      )}
    </section>
  );
}

function SearchTopBar({
  data,
  routeState,
}: {
  data: SearchInspectData | null;
  routeState: SearchRouteState;
}) {
  const resultKind = data?.query.result_kind ?? "pending";
  return (
    <header className="search-intel-topbar">
      <div className="search-intel-titleline">
        <span>case inspect</span>
        <h2>Search Intel</h2>
        <strong>{routeState.q || "empty query"}</strong>
      </div>
      <div className="search-route-meta">
        <code>{resultKind}</code>
        <code>{data?.query.window ?? routeState.window}</code>
        <code>{data?.query.scope ?? routeState.scope}</code>
      </div>
    </header>
  );
}

function SearchIntelSidebar({
  data,
  routeState,
  onRouteChange,
}: {
  data: SearchInspectData;
  routeState: SearchRouteState;
  onRouteChange: (patch: Partial<SearchRouteState>) => void;
}) {
  const selectedKey = candidateKey(data.resolver.selected_target ?? null);
  const navItems = navForResult(data.query.result_kind);
  const visibleCandidates = data.resolver.target_candidates.slice(0, 6);
  const hiddenCandidateCount = Math.max(
    0,
    data.resolver.target_candidates.length - visibleCandidates.length,
  );

  return (
    <aside className="search-intel-sidebar" aria-label="Search Intel controls">
      <section className="search-side-panel search-side-query">
        <span>query</span>
        <b>{data.query.q || routeState.q}</b>
        <small>{data.query.normalized_q || "no normalization"}</small>
      </section>

      <section className="search-side-panel">
        <span>window</span>
        <div className="search-segmented" role="group" aria-label="search window">
          {WINDOW_OPTIONS.map((window) => (
            <button
              aria-pressed={routeState.window === window}
              className={routeState.window === window ? "active" : ""}
              key={window}
              onClick={() => onRouteChange({ window })}
              type="button"
            >
              {window}
            </button>
          ))}
        </div>
      </section>

      <section className="search-side-panel">
        <span>scope</span>
        <div className="search-segmented two" role="group" aria-label="search scope">
          {SCOPE_OPTIONS.map((scope) => (
            <button
              aria-pressed={routeState.scope === scope}
              className={routeState.scope === scope ? "active" : ""}
              key={scope}
              onClick={() => onRouteChange({ scope })}
              type="button"
            >
              {scope}
            </button>
          ))}
        </div>
      </section>

      <section className="search-side-panel">
        <span>resolver</span>
        <b>{Math.round(data.resolver.confidence * 100)}% confidence</b>
        <div className="search-side-reasons">
          {data.resolver.reasons.map((reason) => (
            <code key={reason}>{reason}</code>
          ))}
        </div>
      </section>

      <section className="search-side-panel">
        <span>candidates</span>
        <div className="search-sidebar-candidates">
          {visibleCandidates.length ? (
            visibleCandidates.map((candidate) => (
              <div
                className={
                  candidateKey(candidate) === selectedKey
                    ? "search-sidebar-candidate selected"
                    : "search-sidebar-candidate"
                }
                key={candidateKey(candidate)}
              >
                <b>
                  {candidate.symbol ? `$${candidate.symbol}` : shortTarget(candidate.target_id)}
                </b>
                <small>{candidate.target_type}</small>
                <code>{candidate.status}</code>
              </div>
            ))
          ) : (
            <small>no target candidates</small>
          )}
          {hiddenCandidateCount ? <small>+{hiddenCandidateCount} more in compare</small> : null}
        </div>
      </section>

      <nav className="search-side-panel search-side-nav" aria-label="Search sections">
        <span>sections</span>
        {navItems.map((item) => (
          <a href={`#${item.id}`} key={item.id}>
            {item.label}
          </a>
        ))}
      </nav>
    </aside>
  );
}

function SearchResultBody({ data }: { data: SearchInspectData }) {
  if (data.query.result_kind === "token_result" && data.token_result) {
    return <TokenResult data={data} result={data.token_result} />;
  }
  if (data.query.result_kind === "ambiguous_result" && data.ambiguous_result) {
    return <AmbiguousResult data={data} result={data.ambiguous_result} />;
  }
  if (data.query.result_kind === "topic_result" && data.topic_result) {
    return <TopicResult data={data} result={data.topic_result} />;
  }
  return <div className="search-empty-state">没有可展示的 search 结果。</div>;
}

function TokenResult({ data, result }: { data: SearchInspectData; result: SearchTokenResult }) {
  const [selectedStageId, setSelectedStageId] = useState<string>("all");
  const radar = useMemo(() => radarSummary(result), [result]);

  return (
    <div className="search-content">
      <section className="search-case-header" id="overview">
        <div>
          <span>token case</span>
          <h3>
            {result.target.symbol
              ? `$${result.target.symbol}`
              : shortTarget(result.target.target_id)}
          </h3>
        </div>
        <div className="search-case-meta">
          <code>{result.target.target_type}</code>
          <code>{result.target.chain_id ?? radar.marketVenue ?? "target"}</code>
          <code>{result.market_overlay.price_series_type}</code>
        </div>
        <p>{identityLine(result.target, result.market_overlay)}</p>
      </section>

      <MetricStrip
        metrics={[
          {
            label: "decision",
            value: radar.decision ?? result.agent_brief.bull_bear.stance,
            detail: radar.rankScore
              ? `${formatScore(radar.rankScore)} / 100`
              : "deterministic brief",
            tone: "positive",
          },
          {
            label: `${data.query.window} posts`,
            value: compactNumber(result.timeline.summary.posts),
            detail: `${compactNumber(result.posts.returned_count)} shown`,
          },
          {
            label: "authors",
            value: compactNumber(result.timeline.summary.authors),
            detail: `top ${formatPercentShare(result.timeline.summary.top_author_share)}`,
          },
          {
            label: "watched",
            value: compactNumber(result.timeline.summary.watched_posts ?? 0),
            detail: "matched accounts",
            tone: result.timeline.summary.watched_posts ? "positive" : "warning",
          },
          {
            label: "phase",
            value: formatPropagationPhase(result.timeline.summary.phase),
            detail: result.timeline.summary.phase,
          },
          {
            label: radar.primaryMarketLabel,
            value: radar.primaryMarketValue,
            detail: radar.primaryMarketDetail,
            tone: radar.primaryMarketTone,
          },
          {
            label: "market",
            value: radar.marketHealth,
            detail: radar.marketVenue ?? "anchor only",
            tone:
              radar.marketHealth === "ready" || radar.marketHealth === "live"
                ? "positive"
                : "warning",
          },
          {
            label: "data health",
            value: radar.dataHealthLine,
            detail: radar.gateLine,
          },
        ]}
      />

      <div className="search-content-grid">
        <div className="search-primary-stack">
          <SearchTimelinePanel
            activeStageId={selectedStageId}
            marketOverlay={result.market_overlay}
            timeline={result.timeline}
            onStageSelect={setSelectedStageId}
          />
          <SearchTwitterResults
            selectedStageId={selectedStageId}
            title={`${data.query.window} Evidence Stream`}
            posts={result.posts.items}
            hasMore={result.posts.has_more}
            onSelectedStageChange={setSelectedStageId}
          />
        </div>
        <aside className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
          <SearchRadarPanel radarItem={result.radar_item} />
        </aside>
      </div>
    </div>
  );
}

function TopicResult({ data, result }: { data: SearchInspectData; result: SearchTopicResult }) {
  return (
    <div className="search-content">
      <section className="search-case-header" id="overview">
        <div>
          <span>topic case</span>
          <h3>{data.query.q}</h3>
        </div>
        <div className="search-case-meta">
          <code>{data.query.result_kind}</code>
          <code>{data.query.window}</code>
          <code>{data.query.scope}</code>
        </div>
        <p>Topic 结果只展示语料聚合，不自动推断为单一 token。</p>
      </section>

      <MetricStrip
        metrics={[
          { label: "result", value: "topic", detail: "no unique target" },
          {
            label: `${data.query.window} posts`,
            value: compactNumber(result.summary.posts),
            detail: "search hits",
          },
          {
            label: "authors",
            value: compactNumber(result.summary.authors),
            detail: "unique handles",
          },
          {
            label: "resolver",
            value: `${Math.round(data.resolver.confidence * 100)}%`,
            detail: "topic confidence",
          },
        ]}
      />

      <div className="search-content-grid">
        <div className="search-primary-stack">
          <SearchTopicTimeline items={result.items} />
          <SearchTwitterResults title="Topic Evidence" items={result.items} />
        </div>
        <aside className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </aside>
      </div>
    </div>
  );
}

function AmbiguousResult({
  data,
  result,
}: {
  data: SearchInspectData;
  result: SearchAmbiguousResult;
}) {
  return (
    <div className="search-content">
      <section className="search-case-header" id="overview">
        <div>
          <span>ambiguous case</span>
          <h3>{data.query.q}</h3>
        </div>
        <div className="search-case-meta">
          <code>{result.candidates.length} candidates</code>
          <code>no auto pick</code>
        </div>
        <p>多个候选存在时，页面保留原始 query 和 topic evidence，不静默选择 token。</p>
      </section>

      <section className="search-panel search-candidate-compare">
        <header>
          <h3>Candidate Compare</h3>
          <span>{result.candidates.length} candidates</span>
        </header>
        <div className="search-candidate-grid">
          {result.candidates.map((candidate) => (
            <article key={candidateKey(candidate)}>
              <b>{candidate.symbol ? `$${candidate.symbol}` : shortTarget(candidate.target_id)}</b>
              <span>{candidate.target_type}</span>
              <code>{candidate.status}</code>
              <small>{candidate.reason}</small>
              <p>{identityLine(candidate, {})}</p>
            </article>
          ))}
        </div>
      </section>

      <div className="search-content-grid">
        <div className="search-primary-stack">
          <SearchTopicTimeline items={result.items} />
          <SearchTwitterResults title="Ambiguous Evidence" items={result.items} />
        </div>
        <aside className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </aside>
      </div>
    </div>
  );
}

type Metric = {
  label: string;
  value: string;
  detail?: string;
  tone?: "positive" | "warning" | "negative";
};

function MetricStrip({ metrics }: { metrics: Metric[] }) {
  return (
    <section className="search-metric-strip" aria-label="Search metrics">
      {metrics.map((metric) => (
        <div className={metric.tone ? `tone-${metric.tone}` : ""} key={metric.label}>
          <span>{metric.label}</span>
          <b>{metric.value}</b>
          {metric.detail ? <em>{metric.detail}</em> : null}
        </div>
      ))}
    </section>
  );
}

function SearchTopicTimeline({ items }: { items: SearchTopicResult["items"] }) {
  const buckets = useMemo(() => topicBuckets(items), [items]);
  const peak = Math.max(...buckets.map((bucket) => bucket.posts), 1);

  return (
    <section className="search-panel search-topic-timeline" id="timeline">
      <header>
        <h3>Topic Mention Timeline</h3>
        <span>{buckets.length} buckets</span>
      </header>
      <div className="search-topic-bars" aria-label="topic buckets">
        {buckets.map((bucket) => (
          <div key={bucket.startMs}>
            <i style={{ height: `${Math.max(8, (bucket.posts / peak) * 100)}%` }} />
            <span>{bucket.posts}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SearchRadarPanel({ radarItem }: { radarItem?: Record<string, unknown> | null }) {
  const radar = asRecord(radarItem);
  const score = asRecord(radar.score);
  const snapshot = asRecord(radar.factor_snapshot);
  const composite = asRecord(snapshot.composite);
  const gates = asRecord(snapshot.gates);
  const dataHealth = nonEmptyRecord(radar.data_health) ?? asRecord(snapshot.data_health);
  const familyScores = nonEmptyRecord(score.family_scores) ?? asRecord(composite.family_scores);
  const entries = Object.entries(familyScores).slice(0, 6);

  return (
    <section className="search-panel search-radar-panel" id="score">
      <header>
        <h3>Score / Data Health</h3>
        <span>{radarItem ? "radar row" : "not in current radar"}</span>
      </header>
      {radarItem ? (
        <>
          <div className="search-score-summary">
            <div>
              <span>rank</span>
              <b>{formatScore(numberValue(score.rank_score ?? composite.rank_score))}</b>
            </div>
            <div>
              <span>decision</span>
              <b>{stringValue(score.recommended_decision ?? composite.recommended_decision)}</b>
            </div>
            <div>
              <span>gate</span>
              <b>{stringValue(gates.max_decision)}</b>
            </div>
          </div>
          {entries.length ? (
            <div className="search-score-families">
              {entries.map(([key, value]) => (
                <div key={key}>
                  <span>{key.replaceAll("_", " ")}</span>
                  <b>{formatScore(numberValue(value))}</b>
                </div>
              ))}
            </div>
          ) : null}
          <div className="search-data-health">
            {Object.entries(dataHealth).map(([key, value]) => (
              <code key={key}>
                {key}: {stringValue(value)}
              </code>
            ))}
          </div>
        </>
      ) : (
        <div className="search-empty-state compact">
          当前 window/scope 下没有匹配 radar row。证据和 agent brief 仍然可读。
        </div>
      )}
    </section>
  );
}

function radarSummary(result: SearchTokenResult) {
  const radar = asRecord(result.radar_item);
  const radarTarget = asRecord(radar.target);
  const score = asRecord(radar.score);
  const snapshot = asRecord(radar.factor_snapshot);
  const composite = asRecord(snapshot.composite);
  const gates = asRecord(snapshot.gates);
  const dataHealth = nonEmptyRecord(radar.data_health) ?? asRecord(snapshot.data_health);
  const live = asRecord(radar.live_market);
  const anchor = asRecord(radar.anchor_price);
  const snapshotMarket = asRecord(snapshot.market);
  const marketOverlay = asRecord(result.market_overlay);
  const firstBucketPrice = result.timeline.buckets.find((bucket) => bucket.price?.price_usd)?.price;
  const candleClose = latestCandleClose(result.market_overlay.candles);
  const isDexMarket =
    result.target.target_type === "Asset" || stringValue(radarTarget.target_type) === "Asset";
  const liveMarketCap = numberValue(live.market_cap_usd);
  const anchoredMarketCap = numberValue(snapshotMarket.market_cap_usd);
  const marketCap = liveMarketCap ?? anchoredMarketCap;
  const marketCapStatus =
    liveMarketCap !== null
      ? stringValue(live.status)
      : anchoredMarketCap !== null
        ? "anchored"
        : "missing";
  const price =
    candleClose ??
    numberValue(live.price_usd) ??
    numberValue(anchor.price_usd) ??
    numberValue(firstBucketPrice?.price_usd);
  const priceStatus =
    stringValue(marketOverlay.candle_status) === "ready"
      ? "ohlc ready"
      : stringValue(live.status) !== "-"
        ? stringValue(live.status)
        : stringValue(anchor.status);
  const provider = stringValue(live.provider ?? anchor.provider ?? marketOverlay.provider);
  const primaryMarketLabel = isDexMarket ? "market cap" : "price";
  const primaryMarketValue = isDexMarket
    ? marketCap === null
      ? "-"
      : formatUsdCompact(marketCap)
    : price === null
      ? "-"
      : formatTokenPriceUsd(price);
  const primaryMarketDetail = isDexMarket
    ? marketCap === null
      ? `${priceStatus} · cap missing`
      : `${marketCapStatus} · ${provider}`
    : priceStatus !== "-"
      ? `${priceStatus} · ${provider}`
      : "message anchor only";
  const marketHealth =
    stringValue(marketOverlay.candle_status) === "ready"
      ? "ready"
      : stringValue(dataHealth.market) !== "-"
        ? stringValue(dataHealth.market)
        : priceStatus;

  return {
    decision: stringValue(score.recommended_decision ?? composite.recommended_decision),
    rankScore: numberValue(score.rank_score ?? composite.rank_score),
    gateLine:
      stringValue(gates.max_decision) !== "-"
        ? `gate ${stringValue(gates.max_decision)}`
        : "gate unavailable",
    primaryMarketLabel,
    primaryMarketValue,
    primaryMarketDetail,
    primaryMarketTone: isDexMarket
      ? marketCap === null
        ? "warning"
        : "positive"
      : price
        ? "positive"
        : "warning",
    marketHealth,
    marketVenue: stringValue(
      marketOverlay.native_market_id ??
        marketOverlay.chain_id ??
        marketOverlay.provider ??
        marketOverlay.pricefeed_id,
    ),
    dataHealthLine:
      Object.entries(dataHealth)
        .slice(0, 3)
        .map(([key, value]) => `${key}:${String(value)}`)
        .join(" · ") || "not ranked",
  } satisfies {
    decision: string;
    rankScore: number | null;
    gateLine: string;
    primaryMarketLabel: string;
    primaryMarketValue: string;
    primaryMarketDetail: string;
    primaryMarketTone: "positive" | "warning";
    marketHealth: string;
    marketVenue: string;
    dataHealthLine: string;
  };
}

function topicBuckets(items: SearchTopicResult["items"]) {
  const times = items
    .map((item) => item.event.received_at_ms)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!times.length) {
    return [{ startMs: 0, posts: 0 }];
  }
  const min = Math.min(...times);
  const bucketMs = 60 * 60 * 1000;
  const grouped = new Map<number, number>();
  for (const time of times) {
    const startMs = min + Math.floor((time - min) / bucketMs) * bucketMs;
    grouped.set(startMs, (grouped.get(startMs) ?? 0) + 1);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([startMs, posts]) => ({ startMs, posts }));
}

function navForResult(kind: SearchInspectData["query"]["result_kind"]) {
  if (kind === "token_result") {
    return [
      { id: "overview", label: "Overview" },
      { id: "timeline", label: "Timeline" },
      { id: "evidence", label: "Evidence" },
      { id: "agent-brief", label: "Agent Brief" },
      { id: "score", label: "Score" },
    ];
  }
  return [
    { id: "overview", label: "Overview" },
    { id: "timeline", label: "Timeline" },
    { id: "evidence", label: "Evidence" },
    { id: "agent-brief", label: "Agent Brief" },
  ];
}

function identityLine(candidate: SearchTargetCandidate, marketOverlay: Record<string, unknown>) {
  const chain = candidate.chain_id ?? stringValue(marketOverlay.chain_id);
  const address = candidate.address ?? stringValue(marketOverlay.address);
  const nativeMarket = stringValue(marketOverlay.native_market_id);
  if (candidate.target_type === "CexToken" && nativeMarket !== "-") {
    return `${nativeMarket} · ${candidate.target_id}`;
  }
  if (address && address !== "-") {
    return `${chain || "chain"} · ${shortAddress(address)}`;
  }
  return candidate.target_id;
}

function shortTarget(value: string) {
  return value.length > 28 ? `${value.slice(0, 14)}...${value.slice(-8)}` : value;
}

function candidateKey(candidate: SearchTargetCandidate | null) {
  if (!candidate) return "";
  return `${candidate.target_type}:${candidate.target_id}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function nonEmptyRecord(value: unknown): Record<string, unknown> | null {
  const record = asRecord(value);
  return Object.keys(record).length ? record : null;
}

function latestCandleClose(value: unknown): number | null {
  if (!Array.isArray(value)) {
    return null;
  }
  for (let index = value.length - 1; index >= 0; index -= 1) {
    const close = numberValue(asRecord(value[index]).close);
    if (close !== null) {
      return close;
    }
  }
  return null;
}

function stringValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "-";
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}
