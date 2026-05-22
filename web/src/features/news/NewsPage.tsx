import { formatRelativeTime } from "@lib/format";
import type {
  NewsAgentBrief,
  NewsAgentBriefView,
  NewsAgentDataGap,
  NewsAgentEvidenceRef,
  NewsFactLane,
  NewsItemDetail,
  NewsRow,
  NewsTokenLane,
} from "@shared/model/newsIntel";
import { newsLifecycleLabel } from "@shared/model/newsIntel";
import { newsItemPath, newsPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import * as Tabs from "@shared/ui/tabs";
import {
  ArrowLeft,
  Bot,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  ShieldAlert,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import "./news.css";
import "./NewsDetail.css";
import {
  agentBriefLabel,
  agentBriefMissingText,
  formatAgentBriefStrength,
  inferNewsInstruments,
} from "./newsViewModel";
import { NEWS_PAGE_SIZE, useNewsItemWithToken, useNewsPageWithToken } from "./useNewsPage";

type NewsPageProps = {
  token: string;
  newsItemId?: string | null;
};

const EMPTY_NEWS_ROWS: NewsRow[] = [];

type NewsDirectionFilter = "all" | "bullish" | "bearish";

export function NewsPage({ token, newsItemId = null }: NewsPageProps) {
  if (newsItemId) {
    return <NewsItemRoute newsItemId={newsItemId} token={token} />;
  }
  return <NewsQueueRoute token={token} />;
}

function NewsQueueRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const [directionFilter, setDirectionFilter] = useState<NewsDirectionFilter>("all");
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const direction = directionFilter === "all" ? null : directionFilter;
  const cursor = cursorStack[cursorStack.length - 1] ?? null;
  const query = useNewsPageWithToken(token, { cursor, direction, limit: NEWS_PAGE_SIZE });
  const rows = query.data?.items ?? EMPTY_NEWS_ROWS;
  const hasNextPage = Boolean(query.data?.next_cursor);
  const showLoading = query.isLoading && rows.length === 0;
  const showEmpty = !query.isLoading && !query.isError && rows.length === 0;
  const resultLabel = rows.length
    ? `${rows.length} loaded${hasNextPage ? " · next page" : " · latest"}`
    : query.isLoading
      ? "loading"
      : "no rows";
  const summary = useMemo(() => buildQueueSummary(rows), [rows]);
  const pageNumber = cursorStack.length;

  return (
    <section className="radar-panel news-panel news-queue-shell" aria-label="News intel">
      <div aria-label="News intel page container" className="news-table-wrap">
        <div className="news-control-bar">
          <NewsDirectionTabs
            value={directionFilter}
            onChange={(next) => {
              setDirectionFilter(next);
              setCursorStack([null]);
            }}
          />
          <NewsPager
            hasNextPage={hasNextPage}
            isFetching={query.isFetching}
            pageNumber={pageNumber}
            rowCount={rows.length}
            onNext={() => {
              const nextCursor = query.data?.next_cursor;
              if (nextCursor) {
                setCursorStack((stack) => [...stack, nextCursor]);
              }
            }}
            onPrevious={() => {
              setCursorStack((stack) => (stack.length > 1 ? stack.slice(0, -1) : stack));
            }}
          />
        </div>
        {showLoading ? (
          <PageState.Loading layout="panel" rows={8} label="loading news table" />
        ) : null}
        {query.isError ? <PageState.Error error={query.error ?? "News unavailable"} /> : null}
        {showEmpty ? (
          <PageState.Empty
            title="No news rows"
            hint="The API returned no paged items for the current queue."
          />
        ) : null}
        {!showLoading && !query.isError && rows.length ? (
          <PageState.Stale updating={query.isFetching && !query.isLoading}>
            <div className="news-desk">
              <NewsQueueSummary resultLabel={resultLabel} summary={summary} />
              <div className="news-feed-head" aria-hidden="true">
                <span>Time</span>
                <span>Brief</span>
                <span>Direction</span>
                <span>Decision</span>
                <span>Evidence/Gaps</span>
              </div>
              <div className="news-desk-feed" role="list" aria-label="news decision feed">
                {rows.map((row, index) => (
                  <NewsDeskRow
                    item={row}
                    key={`${row.news_item_id}:${row.latest_at_ms ?? "time"}:${index}`}
                    onOpen={() => navigate(newsItemPath(row.news_item_id))}
                  />
                ))}
              </div>
            </div>
          </PageState.Stale>
        ) : null}
      </div>
    </section>
  );
}

function NewsDirectionTabs({
  value,
  onChange,
}: {
  value: NewsDirectionFilter;
  onChange: (value: NewsDirectionFilter) => void;
}) {
  return (
    <Tabs.Root
      className="news-direction-tabs"
      activationMode="manual"
      value={value}
      onValueChange={(next) => onChange(next as NewsDirectionFilter)}
    >
      <Tabs.List aria-label="News direction" className="news-direction-tab-list">
        <Tabs.Trigger value="all" onClick={() => onChange("all")}>
          All
        </Tabs.Trigger>
        <Tabs.Trigger value="bullish" onClick={() => onChange("bullish")}>
          Bullish
        </Tabs.Trigger>
        <Tabs.Trigger value="bearish" onClick={() => onChange("bearish")}>
          Bear
        </Tabs.Trigger>
      </Tabs.List>
    </Tabs.Root>
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
        type="button"
        disabled={pageNumber <= 1 || isFetching}
        onClick={onPrevious}
      >
        <ChevronLeft aria-hidden />
        Previous
      </button>
      <span className="news-page-label">
        Page {pageNumber} · {rowCount}/{NEWS_PAGE_SIZE}
      </span>
      <button
        aria-label="Next news page"
        className="news-page-button"
        type="button"
        disabled={!hasNextPage || isFetching}
        onClick={onNext}
      >
        Next
        <ChevronRight aria-hidden />
      </button>
    </nav>
  );
}

function NewsItemRoute({ token, newsItemId }: { token: string; newsItemId: string }) {
  const query = useNewsItemWithToken(token, newsItemId);
  const item = query.data ?? null;
  const showLoading = query.isLoading && !item;

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

      {showLoading ? (
        <PageState.Loading layout="panel" rows={8} label="loading news item" />
      ) : null}
      {query.isError ? <PageState.Error error={query.error ?? "News item unavailable"} /> : null}
      {!showLoading && !query.isError && !item ? (
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

type NewsQueueSummaryView = {
  driverLabel: string;
  gapLabel: string;
  readyLabel: string;
};

function buildQueueSummary(rows: NewsRow[]): NewsQueueSummaryView {
  const readyCount = rows.filter((row) => row.agent_brief?.status === "ready").length;
  const driverCount = rows.filter((row) => row.agent_brief?.decision_class === "driver").length;
  const gapCount = rows.reduce(
    (total, row) =>
      total + (row.agent_brief?.data_gap_count ?? row.agent_brief?.data_gaps?.length ?? 0),
    0,
  );
  return {
    driverLabel: `${driverCount}/${rows.length}`,
    gapLabel: String(gapCount),
    readyLabel: `${readyCount}/${rows.length}`,
  };
}

function NewsQueueSummary({
  resultLabel,
  summary,
}: {
  resultLabel: string;
  summary: NewsQueueSummaryView;
}) {
  return (
    <div className="news-queue-summary" aria-label="news queue summary">
      <SummaryMetric icon={<Bot aria-hidden />} label="Agent ready" value={summary.readyLabel} />
      <SummaryMetric icon={<Target aria-hidden />} label="Drivers" value={summary.driverLabel} />
      <SummaryMetric icon={<ShieldAlert aria-hidden />} label="Gaps" value={summary.gapLabel} />
      <SummaryMetric icon={<Clock3 aria-hidden />} label="Loaded" value={resultLabel} />
    </div>
  );
}

function SummaryMetric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="news-summary-metric">
      {icon}
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function DirectionIcon({ direction }: { direction: string }) {
  const normalized = direction.toLowerCase();
  if (normalized.includes("bull")) {
    return <TrendingUp aria-hidden className="news-direction-icon is-bullish" />;
  }
  if (normalized.includes("bear")) {
    return <TrendingDown aria-hidden className="news-direction-icon is-bearish" />;
  }
  return <Target aria-hidden className="news-direction-icon is-neutral" />;
}

function NewsDeskRow({ item, onOpen }: { item: NewsRow; onOpen: () => void }) {
  const brief = item.agent_brief;
  const decision = brief?.decision_class || agentBriefLabel(brief?.status);
  const direction = brief?.direction || agentBriefLabel(brief?.status);
  const evidenceCount = brief?.evidence_refs?.length ?? 0;
  const dataGapCount = brief?.data_gap_count ?? brief?.data_gaps?.length ?? 0;
  const tokens = item.token_lanes ?? [];
  const facts = item.fact_lanes ?? [];

  return (
    <button
      aria-label={`Open news item ${item.headline}`}
      className={`news-desk-row ${decisionTone(decision)}`}
      type="button"
      onClick={onOpen}
    >
      <div className="news-time-cell">
        <b>{item.latest_at_ms ? `${formatRelativeTime(item.latest_at_ms)} ago` : "time missing"}</b>
        <span>{newsLifecycleLabel(item.lifecycle_status)}</span>
        <small>{item.source_domain || "source unknown"}</small>
      </div>

      <div className="news-event-cell">
        <div className="news-row-kicker">
          <span>{agentBriefLabel(brief?.status)}</span>
          {item.story_id ? <span>story linked</span> : <span>single item</span>}
          {tokens.slice(0, 2).map((token, index) => (
            <span key={`${token.symbol ?? token.target_id ?? "token"}-${index}`}>
              {token.symbol || token.target_id || "token"}
            </span>
          ))}
        </div>
        <strong>{item.headline}</strong>
        <p className="news-agent-line">{brief?.summary_zh || agentBriefMissingText(brief)}</p>
        <p className="news-market-line">
          {brief?.market_read_zh || item.summary || "No market read persisted."}
        </p>
      </div>

      <div className="news-instrument-cell">
        <DirectionIcon direction={direction} />
        <strong>{direction}</strong>
        <span>
          bull {formatAgentBriefStrength(brief?.bull_strength)} / bear{" "}
          {formatAgentBriefStrength(brief?.bear_strength)}
        </span>
      </div>

      <div className="news-route-cell">
        <span className={`news-route-pill ${decisionTone(decision)}`}>{decision}</span>
        <small>
          {facts.length} fact {facts.length === 1 ? "lane" : "lanes"}
        </small>
      </div>

      <div className="news-next-cell">
        <strong>
          {evidenceCount} evidence / {dataGapCount} gaps
        </strong>
        <span>
          {firstAvailable(brief?.data_gaps?.map(dataGapLabel)) ||
            firstEvidenceLabel(brief?.evidence_refs) ||
            "evidence pending"}
        </span>
      </div>
    </button>
  );
}

function NewsItemDetailView({ item }: { item: NewsItemDetail }) {
  const instruments = inferNewsInstruments(item);
  const facts = item.fact_lanes?.length ? item.fact_lanes : (item.fact_candidates ?? []);
  const tokens = item.token_lanes ?? [];
  const brief = item.agent_brief;
  const decision = brief?.decision_class || agentBriefLabel(brief?.status);
  const direction = brief?.direction || agentBriefLabel(brief?.status);
  const evidenceCount = brief?.evidence_refs?.length ?? 0;
  const dataGapCount = brief?.data_gap_count ?? brief?.data_gaps?.length ?? 0;

  return (
    <article className="news-detail">
      <header className="news-detail-hero news-agent-command">
        <div className="news-hero-grid">
          <div className="news-hero-agent">
            <div className="news-row-kicker">
              <span>Agent memo</span>
              <span className={decisionTone(decision)}>{decision}</span>
              <span>{direction}</span>
            </div>
            <h2>{brief?.summary_zh || item.headline}</h2>
            <p>{brief?.market_read_zh || agentBriefMissingText(brief)}</p>
          </div>
          <div className="news-source-card">
            <span>Evidence packet</span>
            <b>
              {evidenceCount} refs / {dataGapCount} gaps
            </b>
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

      <div className="news-decision-strip" aria-label="news trading decision context">
        <DecisionMetric
          label="Direction"
          value={direction}
          hint={`bull ${formatAgentBriefStrength(brief?.bull_strength)} / bear ${formatAgentBriefStrength(brief?.bear_strength)}`}
        />
        <DecisionMetric label="Decision" value={decision} hint="Persisted shadow triage label" />
        <DecisionMetric
          label="Evidence"
          value={`${evidenceCount} refs`}
          hint={`${dataGapCount} data gaps`}
        />
      </div>

      <div className="news-detail-grid">
        <div className="news-detail-main">
          <AgentBriefPanel brief={brief} run={item.agent_run} />

          <section className="news-detail-section">
            <div className="news-section-heading">
              <h3>Market map</h3>
              <span className="news-section-note">{instruments.length} lanes</span>
            </div>
            <div className="news-instrument-grid">
              {instruments.map((instrument) => (
                <div
                  className="news-instrument-card"
                  key={`${instrument.label}-${instrument.type}`}
                >
                  <div>
                    <b>{instrument.label}</b>
                    <span>{instrument.type}</span>
                  </div>
                  <strong>{instrument.priceState}</strong>
                  <p>{instrument.use}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="news-detail-section">
            <div className="news-section-heading">
              <h3>Source brief</h3>
              <span className="news-section-note">{newsLifecycleLabel(item.lifecycle_status)}</span>
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
            <h3>Story continuity</h3>
            <StoryContinuity item={item} />
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

function AgentBriefPanel({
  brief,
  run,
}: {
  brief?: NewsAgentBrief | null;
  run?: NewsItemDetail["agent_run"];
}) {
  const status = agentBriefLabel(brief?.status);
  const runError = run?.error_message || run?.error || run?.error_class;
  return (
    <section className="news-detail-section news-agent-brief-panel">
      <div className="news-section-heading">
        <h3>Agent brief</h3>
        <span className={`news-route-pill ${briefTone(brief)}`}>{status}</span>
      </div>
      <div className="news-agent-summary">
        <div>
          <span>Summary</span>
          <p>{brief?.summary_zh || agentBriefMissingText(brief)}</p>
        </div>
        <div>
          <span>Market read</span>
          <p>{brief?.market_read_zh || agentBriefMissingText(brief)}</p>
        </div>
      </div>
      <div className="news-agent-view-grid">
        <AgentViewCard title="多头视角" view={brief?.bull_view} strength={brief?.bull_strength} />
        <AgentViewCard title="空头视角" view={brief?.bear_view} strength={brief?.bear_strength} />
      </div>
      <div className="news-agent-list-grid">
        <AgentList
          title="Watch triggers"
          items={brief?.watch_triggers}
          empty="No watch trigger persisted."
        />
        <AgentList
          title="Invalidation"
          items={brief?.invalidation_conditions}
          empty="No invalidation condition persisted."
        />
        <AgentList
          title="Data gaps"
          items={brief?.data_gaps?.map(dataGapLabel)}
          empty="No data gap persisted."
        />
        <AgentList
          title="Evidence refs"
          items={brief?.evidence_refs?.map(evidenceLabel)}
          empty="No evidence ref persisted."
        />
      </div>
      <dl className="news-metadata-list news-agent-audit">
        <div>
          <dt>Run</dt>
          <dd>{brief?.agent_run_id || run?.run_id || "missing"}</dd>
        </div>
        <div>
          <dt>Prompt</dt>
          <dd>{brief?.prompt_version || run?.prompt_version || "missing"}</dd>
        </div>
        <div>
          <dt>Schema</dt>
          <dd>{brief?.schema_version || run?.schema_version || "missing"}</dd>
        </div>
        <div>
          <dt>Input hash</dt>
          <dd>{brief?.input_hash || "missing"}</dd>
        </div>
        <div>
          <dt>Artifact</dt>
          <dd>{brief?.artifact_version_hash || "missing"}</dd>
        </div>
        <div>
          <dt>Computed</dt>
          <dd>
            {brief?.computed_at_ms ? `${formatRelativeTime(brief.computed_at_ms)} ago` : "missing"}
          </dd>
        </div>
        {runError ? (
          <div>
            <dt>Error</dt>
            <dd>{runError}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

function AgentViewCard({
  strength,
  title,
  view,
}: {
  strength?: string | null;
  title: string;
  view?: NewsAgentBriefView | null;
}) {
  return (
    <div className="news-agent-view-card">
      <div>
        <b>{title}</b>
        <span>{formatAgentBriefStrength(view?.strength ?? strength)}</span>
      </div>
      <p>{view?.thesis_zh || "No persisted thesis."}</p>
      <small>
        {(view?.evidence_refs ?? []).map(evidenceLabel).join(" / ") || "No cited evidence."}
      </small>
    </div>
  );
}

function AgentList({ empty, items, title }: { empty: string; items?: string[]; title: string }) {
  const visibleItems = items?.filter(Boolean) ?? [];
  return (
    <div className="news-agent-list">
      <b>{title}</b>
      {visibleItems.length ? (
        <ul>
          {visibleItems.map((item, index) => (
            <li key={`${title}-${item}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </div>
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
  if (!facts.length) {
    return <p className="news-muted-copy">No semantic fact candidate is attached yet.</p>;
  }
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
  if (!tokens.length) {
    return (
      <p className="news-muted-copy">
        No production token identity is linked. Keep this item as context until resolution lands.
      </p>
    );
  }
  return (
    <div className="news-token-list">
      {tokens.map((token, index) => (
        <div
          className="news-token-item"
          key={`${token.symbol ?? token.target_id ?? "token"}-${index}`}
        >
          <b>{token.symbol || token.target_id || "unknown token"}</b>
          <span>{token.resolution_status || token.lane}</span>
          <small>{token.target_type || "target type missing"}</small>
        </div>
      ))}
    </div>
  );
}

function StoryContinuity({ item }: { item: NewsItemDetail }) {
  const members = item.story_members ?? [];
  if (!members.length) {
    return (
      <p className="news-muted-copy">Single-row story. No multi-item continuity is attached.</p>
    );
  }
  return (
    <div className="news-story-list">
      {members.slice(0, 4).map((member, index) => (
        <div className="news-story-item" key={`${member.story_id ?? "story"}-${index}`}>
          <b>{member.representative_title || member.story_id || "story member"}</b>
          <span>{member.status || "status missing"}</span>
          {member.latest_seen_at_ms ? (
            <small>{formatRelativeTime(member.latest_seen_at_ms)} ago</small>
          ) : null}
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
        <dt>Source tier</dt>
        <dd>{item.source?.trust_tier || "unknown"}</dd>
      </div>
      <div>
        <dt>Source role</dt>
        <dd>{item.source?.source_role || "unknown"}</dd>
      </div>
      <div>
        <dt>Story id</dt>
        <dd>{item.story_id || "none"}</dd>
      </div>
    </dl>
  );
}

function decisionTone(decision?: string | null): string {
  const normalized = decision?.toLowerCase() ?? "";
  if (normalized === "driver") return "is-driver";
  if (normalized === "watch") return "is-watch";
  if (normalized === "discard") return "is-discard";
  if (normalized === "context") return "is-context";
  if (normalized === "ready") return "is-linked";
  if (normalized === "insufficient" || normalized === "stale") return "is-gap";
  return "is-context";
}

function briefTone(brief?: NewsAgentBrief | null): string {
  if (brief?.status === "ready") return "is-linked";
  if (brief?.status === "insufficient" || brief?.status === "stale") return "is-gap";
  return "is-context";
}

function firstAvailable(items?: string[]): string {
  return items?.find(Boolean) ?? "";
}

function firstEvidenceLabel(items?: NewsAgentEvidenceRef[]): string {
  return items?.map(evidenceLabel).find(Boolean) ?? "";
}

function evidenceLabel(ref: NewsAgentEvidenceRef): string {
  if (typeof ref === "string") return ref;
  return ref.label || ref.ref || ref.source || ref.quote || "evidence";
}

function dataGapLabel(gap: NewsAgentDataGap): string {
  if (typeof gap === "string") return gap;
  const description = gap.description_zh || gap.description || gap.reason || gap.kind || "data gap";
  return gap.severity ? `${gap.severity} · ${description}` : description;
}

function trimContent(content?: string | null): string | null {
  if (!content) return null;
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return null;
  return normalized.length > 360 ? `${normalized.slice(0, 357)}...` : normalized;
}
