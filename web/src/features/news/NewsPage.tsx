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
import { RemoteState } from "@shared/ui/RemoteState";
import { flexRender, getCoreRowModel, type ColumnDef, useReactTable } from "@tanstack/react-table";
import { ArrowLeft, ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import "./news.css";
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

export function NewsPage({ token, newsItemId = null }: NewsPageProps) {
  if (newsItemId) {
    return <NewsItemRoute newsItemId={newsItemId} token={token} />;
  }
  return <NewsQueueRoute token={token} />;
}

function NewsQueueRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([null]);
  const pageIndex = Math.max(cursorStack.length - 1, 0);
  const cursor = cursorStack[pageIndex] ?? null;
  const query = useNewsPageWithToken(token, { cursor, limit: NEWS_PAGE_SIZE });
  const rows = query.data?.items ?? [];
  const nextCursor = query.data?.next_cursor ?? null;
  const showLoading = query.isLoading && rows.length === 0;
  const showEmpty = !query.isLoading && !query.isError && rows.length === 0;
  const pageStart = rows.length ? pageIndex * NEWS_PAGE_SIZE + 1 : 0;
  const pageEnd = rows.length ? pageStart + rows.length - 1 : 0;
  const resultLabel = rows.length
    ? `${pageStart}-${pageEnd}${nextCursor ? " · more available" : " · latest page"}`
    : query.isLoading
      ? "loading"
      : "no rows";
  const columns = useMemo<ColumnDef<NewsRow>[]>(() => newsColumns(), []);
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row, index) => `${row.news_item_id}:${row.latest_at_ms ?? "time"}:${index}`,
  });

  const goPrev = () => {
    setCursorStack((current) => (current.length > 1 ? current.slice(0, -1) : current));
  };
  const goNext = () => {
    if (!nextCursor) return;
    setCursorStack((current) => [...current, nextCursor]);
  };

  return (
    <section className="radar-panel news-panel" aria-label="News intel">
      <header className="radar-toolbar news-toolbar">
        <div className="radar-scan-title news-toolbar-copy">
          <h2>News</h2>
          <span>{resultLabel}</span>
        </div>
        <div className="news-pagination" aria-label="news pagination">
          <button
            aria-label="Previous news page"
            className="news-page-button"
            disabled={pageIndex === 0 || query.isFetching}
            type="button"
            onClick={goPrev}
          >
            <ChevronLeft aria-hidden />
          </button>
          <span>Page {pageIndex + 1}</span>
          <button
            aria-label="Next news page"
            className="news-page-button"
            disabled={!nextCursor || query.isFetching}
            type="button"
            onClick={goNext}
          >
            <ChevronRight aria-hidden />
          </button>
        </div>
      </header>

      <div className="news-table-wrap">
        {showLoading ? (
          <RemoteState.Loading layout="panel" rows={8} label="loading news table" />
        ) : null}
        {query.isError ? <RemoteState.Error error={query.error ?? "News unavailable"} /> : null}
        {showEmpty ? (
          <RemoteState.Empty
            title="No news rows"
            hint="The API returned no paged items for the current queue."
          />
        ) : null}
        {!showLoading && !query.isError && rows.length ? (
          <RemoteState.Stale updating={query.isFetching}>
            <div className="news-data-table">
              <div>
                {table.getHeaderGroups().map((headerGroup) => (
                  <div className="news-table-head" key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <div className={`news-head-cell ${header.column.id}`} key={header.id}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              <div>
                {table.getRowModel().rows.map((row) => (
                  <button
                    aria-label={`Open news item ${row.original.headline}`}
                    className="news-table-row"
                    key={row.id}
                    type="button"
                    onClick={() => navigate(newsItemPath(row.original.news_item_id))}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <div className={`news-table-cell ${cell.column.id}`} key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </div>
                    ))}
                  </button>
                ))}
              </div>
            </div>
          </RemoteState.Stale>
        ) : null}
      </div>
    </section>
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
        <RemoteState.Loading layout="panel" rows={8} label="loading news item" />
      ) : null}
      {query.isError ? <RemoteState.Error error={query.error ?? "News item unavailable"} /> : null}
      {!showLoading && !query.isError && !item ? (
        <RemoteState.Empty title="News item not found" />
      ) : null}
      {item ? (
        <RemoteState.Stale updating={query.isFetching}>
          <NewsItemDetailView item={item} />
        </RemoteState.Stale>
      ) : null}
    </section>
  );
}

function newsColumns(): ColumnDef<NewsRow>[] {
  return [
    {
      id: "time",
      header: "Time / Source",
      accessorFn: (item) => item.latest_at_ms ?? 0,
      cell: ({ row }) => <TimeSourceCell item={row.original} />,
    },
    {
      id: "brief",
      header: "Brief",
      accessorFn: (item) => item.headline,
      cell: ({ row }) => <BriefCell item={row.original} />,
    },
    {
      id: "direction",
      header: "Direction",
      accessorFn: (item) => item.agent_brief?.direction ?? item.agent_brief?.status ?? "",
      cell: ({ row }) => <DirectionCell item={row.original} />,
    },
    {
      id: "decision",
      header: "Decision",
      accessorFn: (item) => item.agent_brief?.decision_class ?? item.agent_brief?.status ?? "",
      cell: ({ row }) => <DecisionCell item={row.original} />,
    },
    {
      id: "evidence",
      header: "Evidence/Gaps",
      accessorFn: (item) => item.agent_brief?.data_gap_count ?? 0,
      cell: ({ row }) => <EvidenceGapCell item={row.original} />,
    },
  ];
}

function TimeSourceCell({ item }: { item: NewsRow }) {
  return (
    <div className="news-time-cell">
      <b>{item.source_domain || "unknown source"}</b>
      <span>
        {item.latest_at_ms ? `${formatRelativeTime(item.latest_at_ms)} ago` : "time missing"}
      </span>
    </div>
  );
}

function BriefCell({ item }: { item: NewsRow }) {
  const brief = item.agent_brief;
  return (
    <div className="news-event-cell">
      <div className="news-row-kicker">
        <span>{newsLifecycleLabel(item.lifecycle_status)}</span>
        {item.story_id ? <span>story linked</span> : <span>single item</span>}
        <span>{agentBriefLabel(brief?.status)}</span>
      </div>
      <strong>{item.headline}</strong>
      <p>{brief?.summary_zh || agentBriefMissingText(brief)}</p>
    </div>
  );
}

function DirectionCell({ item }: { item: NewsRow }) {
  const brief = item.agent_brief;
  return (
    <div className="news-instrument-cell">
      <strong>{brief?.direction || agentBriefLabel(brief?.status)}</strong>
      <span>
        bull {formatAgentBriefStrength(brief?.bull_strength)} / bear{" "}
        {formatAgentBriefStrength(brief?.bear_strength)}
      </span>
    </div>
  );
}

function DecisionCell({ item }: { item: NewsRow }) {
  const brief = item.agent_brief;
  return (
    <div className="news-route-cell">
      <span className={`news-route-pill ${briefTone(brief)}`}>
        {brief?.decision_class || agentBriefLabel(brief?.status)}
      </span>
      <small>{brief?.market_read_zh || agentBriefMissingText(brief)}</small>
    </div>
  );
}

function EvidenceGapCell({ item }: { item: NewsRow }) {
  const brief = item.agent_brief;
  const evidenceCount = brief?.evidence_refs?.length ?? 0;
  const dataGapCount = brief?.data_gap_count ?? brief?.data_gaps?.length ?? 0;
  return (
    <div className="news-next-cell">
      <strong>
        {evidenceCount} evidence / {dataGapCount} gaps
      </strong>
      <span>
        {firstAvailable(brief?.data_gaps?.map(dataGapLabel)) ||
          firstEvidenceLabel(brief?.evidence_refs)}
      </span>
    </div>
  );
}

function NewsItemDetailView({ item }: { item: NewsItemDetail }) {
  const instruments = inferNewsInstruments(item);
  const facts = item.fact_lanes?.length ? item.fact_lanes : (item.fact_candidates ?? []);
  const tokens = item.token_lanes ?? [];

  return (
    <article className="news-detail">
      <header className="news-detail-hero">
        <div className="news-row-kicker">
          <span>{newsLifecycleLabel(item.lifecycle_status)}</span>
          <span>{item.source_domain || item.source?.source_name || "source unknown"}</span>
          {item.latest_at_ms ? <span>{formatRelativeTime(item.latest_at_ms)} ago</span> : null}
        </div>
        <h2>{item.headline}</h2>
        <p>{item.agent_brief?.market_read_zh || agentBriefMissingText(item.agent_brief)}</p>
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
      </header>

      <div className="news-decision-strip" aria-label="news trading decision context">
        <DecisionMetric
          label="Direction"
          value={item.agent_brief?.direction || agentBriefLabel(item.agent_brief?.status)}
          hint={`bull ${formatAgentBriefStrength(item.agent_brief?.bull_strength)} / bear ${formatAgentBriefStrength(item.agent_brief?.bear_strength)}`}
        />
        <DecisionMetric
          label="Decision"
          value={item.agent_brief?.decision_class || agentBriefLabel(item.agent_brief?.status)}
          hint="Persisted shadow triage label"
        />
        <DecisionMetric
          label="Evidence"
          value={`${item.agent_brief?.evidence_refs?.length ?? 0} refs`}
          hint={`${item.agent_brief?.data_gap_count ?? item.agent_brief?.data_gaps?.length ?? 0} data gaps`}
        />
      </div>

      <div className="news-detail-grid">
        <div className="news-detail-main">
          <AgentBriefPanel brief={item.agent_brief} run={item.agent_run} />

          <section className="news-detail-section">
            <h3>Market map</h3>
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
            <h3>What happened</h3>
            <p>{item.summary || trimContent(item.content) || "No clean summary available yet."}</p>
          </section>

          <section className="news-detail-section">
            <h3>Extracted facts</h3>
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
