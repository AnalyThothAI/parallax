import { useSearchParams } from "react-router-dom";

import { useSearchInspectQuery } from "../api/useSearchInspectQuery";
import { parseSearchRouteState } from "../features/search/searchRouteState";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchTimelinePanel } from "./SearchTimelinePanel";
import { SearchTwitterResults } from "./SearchTwitterResults";

export function SearchIntelPage() {
  const [searchParams] = useSearchParams();
  const routeState = parseSearchRouteState(searchParams);
  const query = useSearchInspectQuery(routeState);
  const data = query.data?.data ?? null;

  return (
    <section className="search-intel-page" aria-label="Search Intel">
      <header className="search-intel-header">
        <div>
          <span>route-backed search result</span>
          <h2>Search Intel</h2>
        </div>
        <div className="search-route-meta">
          <code>{routeState.q || "empty"}</code>
          <code>{routeState.window}</code>
          <code>{routeState.scope}</code>
        </div>
      </header>

      {!routeState.q ? (
        <div className="empty-state">输入搜索词后手动触发检索</div>
      ) : query.isPending ? (
        <div className="empty-state">loading search intel</div>
      ) : query.error ? (
        <div className="empty-state">search intel failed</div>
      ) : data?.query.result_kind === "token_result" && data.token_result ? (
        <TokenResult data={data} />
      ) : data?.query.result_kind === "ambiguous_result" && data.ambiguous_result ? (
        <AmbiguousResult data={data} />
      ) : data?.query.result_kind === "topic_result" && data.topic_result ? (
        <TopicResult data={data} />
      ) : (
        <div className="empty-state">没有可展示的 search 结果</div>
      )}
    </section>
  );
}

type SearchIntelData = NonNullable<ReturnType<typeof useSearchInspectQuery>["data"]>["data"];

function TokenResult({ data }: { data: SearchIntelData }) {
  const result = data.token_result;
  if (!result) return null;
  return (
    <div className="search-result-grid">
      <section className="search-panel search-resolver-panel">
        <header>
          <h3>Query Resolution</h3>
          <span>{data.query.result_kind}</span>
        </header>
        <div className="search-chip-row">
          <span>{result.target.symbol ? `$${result.target.symbol}` : result.target.target_id}</span>
          <span>{result.target.target_type}</span>
          <span>confidence {Math.round(data.resolver.confidence * 100)}%</span>
          <span>candidates {data.resolver.target_candidates.length}</span>
        </div>
      </section>
      <MetricStrip
        metrics={[
          ["agent", result.agent_brief.bull_bear.stance],
          ["24h tweets", String(result.timeline.summary.posts)],
          ["authors", String(result.timeline.summary.authors)],
          ["watched", String(result.timeline.summary.watched_posts ?? 0)],
          ["phase", result.timeline.summary.phase],
          ["market", String(result.market_overlay.price_series_type)],
        ]}
      />
      <div className="search-main-grid">
        <div className="search-left-stack">
          <SearchTimelinePanel timeline={result.timeline} />
          <SearchTwitterResults posts={result.posts.items} />
        </div>
        <div className="search-right-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
}

function TopicResult({ data }: { data: SearchIntelData }) {
  const result = data.topic_result;
  if (!result) return null;
  return (
    <div className="search-result-grid">
      <MetricStrip
        metrics={[
          ["result", "topic"],
          ["24h tweets", String(result.summary.posts)],
          ["authors", String(result.summary.authors)],
        ]}
      />
      <div className="search-main-grid">
        <div className="search-left-stack">
          <SearchTwitterResults items={result.items} />
        </div>
        <div className="search-right-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
}

function AmbiguousResult({ data }: { data: SearchIntelData }) {
  const result = data.ambiguous_result;
  if (!result) return null;
  return (
    <div className="search-result-grid">
      <section className="search-panel">
        <header>
          <h3>Candidate Compare</h3>
          <span>no auto-selection</span>
        </header>
        <div className="search-candidate-list">
          {result.candidates.map((candidate) => (
            <div key={`${candidate.target_type}:${candidate.target_id}`}>
              <b>{candidate.symbol ? `$${candidate.symbol}` : candidate.target_id}</b>
              <span>{candidate.status}</span>
              <code>{candidate.target_id}</code>
            </div>
          ))}
        </div>
      </section>
      <div className="search-main-grid">
        <div className="search-left-stack">
          <SearchTwitterResults items={result.items} />
        </div>
        <div className="search-right-stack">
          <SearchAgentBrief brief={result.agent_brief} />
        </div>
      </div>
    </div>
  );
}

function MetricStrip({ metrics }: { metrics: Array<[string, string]> }) {
  return (
    <section className="search-metric-strip">
      {metrics.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
    </section>
  );
}
