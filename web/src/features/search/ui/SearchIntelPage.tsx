import {
  compactNumber,
  formatPercentShare,
  formatPropagationPhase,
  formatScore,
  shortAddress,
} from "@lib/format";
import type {
  ScopeKey,
  SearchAmbiguousResult,
  SearchInspectData,
  SearchTargetCandidate,
  SearchTopicResult,
  SearchTokenResult,
  WindowKey,
} from "@lib/types";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import { RemoteState } from "@shared/ui/RemoteState";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useSearchInspectQuery } from "../api/useSearchInspectQuery";
import { buildSearchCaseView } from "../model/searchCase";
import { buildSearchRadarSummary } from "../model/searchRadar";
import {
  parseSearchRouteState,
  serializeSearchRouteState,
  type SearchRouteState,
} from "../state/searchRouteState";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchDossier } from "./SearchDossier";
import { SearchMetricStrip } from "./SearchMetricStrip";
import { SearchRadarPanel } from "./SearchRadarPanel";
import { SearchTimelinePanel } from "./SearchTimelinePanel";
import { SearchTopicTimeline } from "./SearchTopicTimeline";
import { SearchTwitterResults } from "./SearchTwitterResults";

const WINDOW_OPTIONS: WindowKey[] = ["5m", "1h", "4h", "24h"];
const SCOPE_OPTIONS: ScopeKey[] = ["all", "matched"];

export function SearchIntelPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const routeState = parseSearchRouteState(searchParams);
  const query = useSearchInspectQuery(routeState);
  const data = query.data?.data ?? null;
  const marketTargets = useMemo(() => searchMarketTargets(data), [data]);
  useMarketSubscription(marketTargets);

  const updateRoute = (patch: Partial<SearchRouteState>) => {
    const next = serializeSearchRouteState({ ...routeState, ...patch });
    navigate({ pathname: "/search", search: `?${next.toString()}` });
  };

  return (
    <section className="search-intel-page" aria-label="Search Intel">
      <SearchTopBar data={data} routeState={routeState} />

      {!routeState.q ? (
        <RemoteState.Empty title="输入 token、CA、@handle 或关键词后手动检索。" />
      ) : query.error ? (
        <RemoteState.Error error={query.error} />
      ) : query.isPending || !data ? (
        <RemoteState.Loading layout="route" rows={5} label="loading search results" />
      ) : (
        <div className="search-workspace">
          <SearchIntelSidebar data={data} routeState={routeState} onRouteChange={updateRoute} />
          <SearchResultBody data={data} />
        </div>
      )}
    </section>
  );
}

function searchMarketTargets(data: SearchInspectData | null) {
  const target = data?.query.result_kind === "token_result" ? data.resolver.selected_target : null;
  if (!target?.target_type || !target.target_id) {
    return [];
  }
  return [{ target_type: target.target_type, target_id: target.target_id }];
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
    <div className="search-intel-sidebar" aria-label="Search Intel controls" role="group">
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
    </div>
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
  return <RemoteState.Empty title="没有可展示的 search 结果。" />;
}

function TokenResult({ data, result }: { data: SearchInspectData; result: SearchTokenResult }) {
  const [selectedStageId, setSelectedStageId] = useState<string>("all");
  const radar = useMemo(() => buildSearchRadarSummary(result), [result]);
  const searchCase = useMemo(() => buildSearchCaseView(data), [data]);

  return (
    <div className="search-content">
      <SearchDossier view={searchCase} />

      <SearchMetricStrip
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
        <div className="search-insight-stack">
          <TokenProfileCard profile={result.profile} />
          <SearchAgentBrief brief={result.agent_brief} />
          <SearchRadarPanel summary={radar} />
        </div>
      </div>
    </div>
  );
}

function TopicResult({ data, result }: { data: SearchInspectData; result: SearchTopicResult }) {
  const searchCase = useMemo(() => buildSearchCaseView(data), [data]);

  return (
    <div className="search-content">
      <SearchDossier view={searchCase} />

      <SearchMetricStrip
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
        <div className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
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
  const searchCase = useMemo(() => buildSearchCaseView(data), [data]);

  return (
    <div className="search-content">
      <SearchDossier view={searchCase} />

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
        <div className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
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

function stringValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "-";
}
