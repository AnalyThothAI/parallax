import { formatRelativeTime } from "@lib/format";
import type {
  NewsAgentBrief,
  NewsFactLane,
  NewsItemDetail,
  NewsRow,
  NewsTokenLane,
} from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import { newsItemPath, newsPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import { ArrowLeft, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenMarketLabel,
} from "./model/newsSignalViewModel";
import "./news.css";
import "./NewsDetail.css";
import { NewsTape } from "./ui/NewsTape";
import { NEWS_PAGE_SIZE, useNewsItemWithToken, useNewsPageWithToken } from "./useNewsPage";

type NewsPageProps = {
  token: string;
  newsItemId?: string | null;
};

const EMPTY_NEWS_ROWS: NewsRow[] = [];
type TokenMode = "with-token" | "no-token";
type SignalFilter = "all" | "bullish" | "bearish" | "neutral";

export function NewsPage({ token, newsItemId = null }: NewsPageProps) {
  if (newsItemId) return <NewsItemRoute newsItemId={newsItemId} token={token} />;
  return <NewsQueueRoute token={token} />;
}

function NewsQueueRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const [tokenMode, setTokenMode] = useState<TokenMode>("with-token");
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");
  const [minScore, setMinScore] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const cursor = cursorStack[cursorStack.length - 1] ?? null;
  const query = useNewsPageWithToken(token, {
    cursor,
    has_token: tokenMode === "with-token",
    limit: NEWS_PAGE_SIZE,
    min_score: minScore,
    q: searchQuery.trim() || null,
    signal: signalFilter === "all" ? null : signalFilter,
  });
  const rows = query.data?.items ?? EMPTY_NEWS_ROWS;
  const resetCursor = () => setCursorStack([null]);

  return (
    <section className="radar-panel news-panel news-queue-shell" aria-label="News intel">
      <div aria-label="News intel page container" className="news-table-wrap">
        <div className="news-compact-controls" aria-label="News filters">
          <div className="news-token-mode" aria-label="Token mode">
            <button
              aria-pressed={tokenMode === "with-token"}
              type="button"
              onClick={() => {
                setTokenMode("with-token");
                resetCursor();
              }}
            >
              有 Token
            </button>
            <button
              aria-pressed={tokenMode === "no-token"}
              type="button"
              onClick={() => {
                setTokenMode("no-token");
                resetCursor();
              }}
            >
              无 Token
            </button>
          </div>
          <div className="news-signal-controls" aria-label="Signal filters">
            {(["all", "bullish", "bearish", "neutral"] as const).map((value) => (
              <button
                aria-pressed={signalFilter === value}
                key={value}
                type="button"
                onClick={() => {
                  setSignalFilter(value);
                  resetCursor();
                }}
              >
                {signalFilterLabel(value)}
              </button>
            ))}
            <button
              aria-pressed={minScore === 70}
              type="button"
              onClick={() => {
                setMinScore((current) => (current === 70 ? null : 70));
                resetCursor();
              }}
            >
              ≥70
            </button>
            <label className="news-search-filter">
              <span>Search</span>
              <input
                aria-label="Search news"
                value={searchQuery}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                  resetCursor();
                }}
                placeholder="headline, token, source"
              />
            </label>
          </div>
          <NewsPager
            hasNextPage={Boolean(query.data?.next_cursor)}
            isFetching={query.isFetching}
            pageNumber={cursorStack.length}
            rowCount={rows.length}
            onNext={() => {
              const nextCursor = query.data?.next_cursor;
              if (nextCursor) setCursorStack((stack) => [...stack, nextCursor]);
            }}
            onPrevious={() =>
              setCursorStack((stack) => (stack.length > 1 ? stack.slice(0, -1) : stack))
            }
          />
        </div>

        {query.isLoading && !rows.length ? (
          <PageState.Loading layout="panel" rows={8} label="loading news tape" />
        ) : null}
        {query.isError ? <PageState.Error error={query.error ?? "News unavailable"} /> : null}
        {!query.isLoading && !query.isError && !rows.length ? (
          <PageState.Empty
            title="No news rows"
            hint="No provider signal rows match the current filters."
          />
        ) : null}
        {!query.isLoading && !query.isError && rows.length ? (
          <PageState.Stale updating={query.isFetching && !query.isLoading}>
            <NewsTape rows={rows} onOpen={(newsId) => navigate(newsItemPath(newsId))} />
          </PageState.Stale>
        ) : null}
      </div>
    </section>
  );
}

function NewsPager({
  hasNextPage,
  isFetching,
  pageNumber,
  rowCount,
  onNext,
  onPrevious,
}: {
  hasNextPage: boolean;
  isFetching: boolean;
  pageNumber: number;
  rowCount: number;
  onNext: () => void;
  onPrevious: () => void;
}) {
  return (
    <nav className="news-pager" aria-label="News pagination">
      <button
        aria-label="Previous news page"
        className="news-page-button"
        disabled={pageNumber <= 1 || isFetching}
        type="button"
        onClick={onPrevious}
      >
        <ChevronLeft aria-hidden />
      </button>
      <span className="news-page-label">
        Page {pageNumber} · {rowCount}/{NEWS_PAGE_SIZE}
      </span>
      <button
        aria-label="Next news page"
        className="news-page-button"
        disabled={!hasNextPage || isFetching}
        type="button"
        onClick={onNext}
      >
        <ChevronRight aria-hidden />
      </button>
    </nav>
  );
}

function NewsItemRoute({ token, newsItemId }: { token: string; newsItemId: string }) {
  const query = useNewsItemWithToken(token, newsItemId);
  const item = query.data ?? null;
  return (
    <section className="radar-panel news-panel news-detail-shell" aria-label="News item detail">
      <header className="radar-toolbar news-toolbar">
        <Link className="news-back-link" to={newsPath()}>
          <ArrowLeft aria-hidden />
          Queue
        </Link>
        <div className="news-pagination" aria-label="news item status">
          <span>{query.isFetching ? "updating" : "live"}</span>
        </div>
      </header>
      {query.isLoading && !item ? (
        <PageState.Loading layout="panel" rows={8} label="loading news item" />
      ) : null}
      {query.isError ? <PageState.Error error={query.error ?? "News item unavailable"} /> : null}
      {!query.isLoading && !query.isError && !item ? (
        <PageState.Empty title="News item not found" />
      ) : null}
      {item ? (
        <PageState.Stale updating={query.isFetching}>
          <NewsItemDetailView item={item} />
        </PageState.Stale>
      ) : null}
    </section>
  );
}

function NewsItemDetailView({ item }: { item: NewsItemDetail }) {
  const facts = item.fact_lanes ?? [];
  const tokens = newsDisplayTokenLanes(item);
  const isProviderSignal = item.signal.source === "provider";
  return (
    <article className="news-detail">
      <header
        className={`news-detail-hero ${isProviderSignal ? "news-provider-command" : "news-agent-command"}`}
      >
        <div className="news-hero-grid">
          <div className="news-hero-agent">
            <div className="news-row-kicker">
              <span>{isProviderSignal ? "Provider signal" : "Agent brief"}</span>
              <span className={newsSignalTone(item.signal)}>{newsSignalLabel(item.signal)}</span>
              <span>{newsSignalScoreLabel(item.signal)}</span>
            </div>
            <h2>{item.signal.summary_zh || item.headline}</h2>
            <p>{item.summary || item.signal.summary_en || "No source summary available."}</p>
          </div>
          <div className="news-source-card">
            <span>Source packet</span>
            <b>{item.signal.method || item.signal.source}</b>
            <p>{item.headline}</p>
            <small>
              {item.source_domain || item.source?.source_name || "source unknown"}
              {item.latest_at_ms ? ` · ${formatRelativeTime(item.latest_at_ms)} ago` : ""}
            </small>
            {item.canonical_url ? (
              <a
                className="news-outline-link"
                href={item.canonical_url}
                rel="noreferrer"
                target="_blank"
              >
                <ExternalLink aria-hidden />
                Original
              </a>
            ) : null}
          </div>
        </div>
      </header>
      <div className="news-decision-strip" aria-label="news provider signal context">
        <DecisionMetric
          label="Direction"
          value={newsSignalLabel(item.signal)}
          hint={item.signal.direction}
        />
        <DecisionMetric
          label="Score"
          value={newsSignalScoreLabel(item.signal)}
          hint={item.signal.status}
        />
        <DecisionMetric
          label="Tokens"
          value={String(tokens.length)}
          hint={newsLifecycleLabel(item.lifecycle_status)}
        />
      </div>
      <div className="news-detail-grid">
        <div className="news-detail-main">
          {isProviderSignal ? (
            <ProviderSignalPanel item={item} />
          ) : (
            <AgentBriefPanel brief={item.agent_brief} />
          )}
          <section className="news-detail-section">
            <div className="news-section-heading">
              <h3>Source brief</h3>
              <span className="news-section-note">
                {item.source?.provider_type || item.provider_type || "provider"}
              </span>
            </div>
            <p>{item.summary || trimContent(item.content) || "No clean summary available yet."}</p>
          </section>
          <section className="news-detail-section">
            <div className="news-section-heading">
              <h3>Extracted facts</h3>
              <span className="news-section-note">{facts.length} candidates</span>
            </div>
            <FactList facts={facts} />
          </section>
        </div>
        <aside className="news-detail-side" aria-label="news item metadata">
          <section className="news-detail-section">
            <h3>Token identity</h3>
            <TokenIdentity tokens={tokens} />
          </section>
          <section className="news-detail-section">
            <h3>Production metadata</h3>
            <MetadataList item={item} />
          </section>
        </aside>
      </div>
    </article>
  );
}

function ProviderSignalPanel({ item }: { item: NewsItemDetail }) {
  return (
    <section className="news-detail-section news-provider-signal-panel">
      <div className="news-section-heading">
        <h3>Provider signal</h3>
        <span className={`news-route-pill ${newsSignalTone(item.signal)}`}>
          {newsSignalLabel(item.signal)}
        </span>
      </div>
      <p>{item.signal.summary_zh || item.signal.summary_en || "Waiting for provider aiRating."}</p>
      <div className="news-token-list">
        {newsDisplayTokenLanes(item).map((token, index) => (
          <div
            className="news-token-item"
            key={`${token.symbol ?? token.target_id ?? "token"}-${index}`}
          >
            <b>{token.symbol || token.target_id || "unknown token"}</b>
            <span>{tokenImpactLabel(token)}</span>
            <small>{token.provider_signal || tokenMarketLabel(token)}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function AgentBriefPanel({ brief }: { brief?: NewsAgentBrief | null }) {
  return (
    <section className="news-detail-section news-agent-brief-panel">
      <div className="news-section-heading">
        <h3>Agent brief</h3>
        <span className="news-route-pill is-context">{brief?.status || "pending"}</span>
      </div>
      <p>{brief?.summary_zh || "Agent fallback is pending for this non-provider row."}</p>
      <p>{brief?.market_read_zh || "No persisted market read."}</p>
    </section>
  );
}

function DecisionMetric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="news-decision-metric">
      <span>{label}</span>
      <b>{value}</b>
      <small>{hint}</small>
    </div>
  );
}

function FactList({ facts }: { facts: NewsFactLane[] }) {
  if (!facts.length)
    return <p className="news-muted-copy">No semantic fact candidate is attached yet.</p>;
  return (
    <div className="news-fact-list">
      {facts.map((fact, index) => (
        <div className="news-fact-item" key={`${fact.event_type ?? "fact"}-${index}`}>
          <div>
            <b>{fact.claim || fact.event_type || "fact candidate"}</b>
            <span>{fact.event_type || "event type missing"}</span>
          </div>
          <strong>{fact.status || "attention"}</strong>
          <p>
            {fact.realis ? `${fact.realis} · ` : ""}
            {Array.isArray(fact.affected_targets)
              ? `${fact.affected_targets.length} affected target candidates`
              : "target extraction pending"}
          </p>
        </div>
      ))}
    </div>
  );
}

function TokenIdentity({ tokens }: { tokens: NewsTokenLane[] }) {
  if (!tokens.length)
    return <p className="news-muted-copy">No production token identity is linked.</p>;
  return (
    <div className="news-token-list">
      {tokens.map((token, index) => (
        <div
          className="news-token-item"
          key={`${token.symbol ?? token.target_id ?? "token"}-${index}`}
        >
          <b>{token.symbol || token.target_id || "unknown token"}</b>
          <span>{token.resolution_status || token.lane}</span>
          <small>{token.target_type || token.market_type || "target type missing"}</small>
        </div>
      ))}
    </div>
  );
}

function MetadataList({ item }: { item: NewsItemDetail }) {
  return (
    <dl className="news-metadata-list">
      <div>
        <dt>Lifecycle</dt>
        <dd>{item.lifecycle_status}</dd>
      </div>
      <div>
        <dt>Provider</dt>
        <dd>
          {item.signal.provider || item.source?.provider_type || item.provider_type || "unknown"}
        </dd>
      </div>
      <div>
        <dt>Method</dt>
        <dd>{item.signal.method || "unknown"}</dd>
      </div>
      <div>
        <dt>Story id</dt>
        <dd>{item.story_id || "none"}</dd>
      </div>
    </dl>
  );
}

function signalFilterLabel(value: SignalFilter): string {
  if (value === "bullish") return "利好";
  if (value === "bearish") return "利空";
  if (value === "neutral") return "中性";
  return "全部";
}

function trimContent(content?: string | null): string | null {
  if (!content) return null;
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return null;
  return normalized.length > 360 ? `${normalized.slice(0, 357)}...` : normalized;
}
