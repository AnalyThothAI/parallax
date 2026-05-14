import { formatRelativeTime } from "@lib/format";
import type {
  WatchlistHandleSummaryData,
  WatchlistHandleTimelineData,
  WatchlistTimelineItem,
  WatchlistTimelineScope,
} from "@lib/types";
import { searchPath } from "@shared/routing/paths";
import { RemoteState } from "@shared/ui/RemoteState";
import { ObsidianPill } from "@shared/ui/case-file";
import {
  AtSign,
  ChevronDown,
  Clock3,
  ExternalLink,
  Radio,
  Search,
  Sparkles,
  TextSearch,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useHandleSummaryQuery } from "../api/useHandleSummaryQuery";
import { useHandleTimelineQuery } from "../api/useHandleTimelineQuery";
import type { WatchlistAccountCase } from "../model/watchlistCase";
import { useWatchlistRouteState } from "../state/watchlistRouteState";
import "./watchlist.css";

type WatchlistPageProps = {
  accountCases: WatchlistAccountCase[];
  token: string;
};

export function WatchlistPage({ accountCases, token }: WatchlistPageProps) {
  const routeState = useWatchlistRouteState(accountCases[0]?.handle ?? null);
  const selectedHandle = routeState.selectedHandle;
  const selectedCase =
    accountCases.find((item) => item.handle === selectedHandle) ??
    (selectedHandle ? emptyAccountCase(selectedHandle) : null);
  const summaryQuery = useHandleSummaryQuery({ handle: selectedHandle, token });
  const timelineQuery = useHandleTimelineQuery({
    handle: selectedHandle,
    scope: routeState.scope,
    token,
  });
  const timelineItems = timelineQuery.data?.pages.flatMap((page) => page.data.items) ?? [];

  if (!selectedCase) {
    return (
      <section className="watchlist-page" aria-label="Watchlist">
        <RemoteState.Empty title="No watchlist handles configured." />
      </section>
    );
  }

  return (
    <section className="watchlist-page" aria-label="Twitter source monitor">
      <div className="watchlist-monitor-shell">
        <WatchlistHero selectedCase={selectedCase} />
        <SignalStrip selectedCase={selectedCase} />
        <HandleTopicSummary query={summaryQuery} />
        <div className="watchlist-monitor-grid">
          <section className="watchlist-evidence-panel" aria-labelledby="watchlist-evidence-title">
            <div className="watchlist-section-head">
              <span>source timeline</span>
              <h3 id="watchlist-evidence-title">Handle intelligence</h3>
              <p>{timelineLeadCopy(routeState.scope, timelineItems.length)}</p>
            </div>
            <HandleTimeline
              query={timelineQuery}
              scope={routeState.scope}
              onScopeChange={routeState.updateScope}
            />
          </section>

          <aside className="watchlist-extraction-panel" aria-label="Extracted account signals">
            <ClusterPanel
              emptyLabel="No token mentions in this window."
              eyebrow="extracted targets"
              items={selectedCase.tokenMentions}
              title="Token mentions"
            />
            <ClusterPanel
              emptyLabel="No narrative clusters in this window."
              eyebrow="hashtags"
              items={selectedCase.narrativeClusters}
              title="Narrative clusters"
            />
            <RiskPanel notes={selectedCase.riskNotes} />
          </aside>
        </div>
      </div>
    </section>
  );
}

function WatchlistHero({ selectedCase }: { selectedCase: WatchlistAccountCase }) {
  return (
    <header className="watchlist-monitor-hero">
      <div className="watchlist-source-mark" aria-hidden>
        <AtSign />
      </div>
      <div className="watchlist-monitor-title">
        <span className="watchlist-kicker">
          <Radio aria-hidden />
          source monitor
        </span>
        <h2>@{selectedCase.handle}</h2>
        <p>{lastSeenCopy(selectedCase.lastSeenAtMs)}</p>
      </div>
      <div className="watchlist-monitor-actions" aria-label="Account actions">
        {selectedCase.searchLinks.map((link) => (
          <Link className="watchlist-action primary" key={link.href} to={link.href}>
            <Search aria-hidden />
            {link.label}
          </Link>
        ))}
        <a
          className="watchlist-action"
          href={`https://x.com/${selectedCase.handle}`}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink aria-hidden />
          Open X
        </a>
      </div>
    </header>
  );
}

function SignalStrip({ selectedCase }: { selectedCase: WatchlistAccountCase }) {
  return (
    <section className="watchlist-signal-strip" aria-label="Monitor status">
      <SignalCard
        detail={selectedCase.unreadCount ? "notifications waiting" : "queue clear"}
        label="Unread"
        tone={selectedCase.unreadCount ? "opportunity" : "neutral"}
        value={selectedCase.unreadCount}
      />
      <SignalCard
        detail={selectedCase.emptyState ?? "captured from public stream"}
        label="Evidence"
        tone={selectedCase.recentEvents.length ? "health" : "neutral"}
        value={selectedCase.recentEvents.length}
      />
      <SignalCard
        detail={topClusterCopy(selectedCase.tokenMentions)}
        label="Tokens"
        tone={selectedCase.tokenMentions.length ? "info" : "neutral"}
        value={selectedCase.tokenMentions.length}
      />
      <SignalCard
        detail={topClusterCopy(selectedCase.narrativeClusters)}
        label="Narratives"
        tone={selectedCase.narrativeClusters.length ? "agent" : "neutral"}
        value={selectedCase.narrativeClusters.length}
      />
    </section>
  );
}

function SignalCard({
  detail,
  label,
  tone,
  value,
}: {
  detail: ReactNode;
  label: string;
  tone: "agent" | "health" | "info" | "neutral" | "opportunity";
  value: ReactNode;
}) {
  return (
    <article className={`watchlist-signal-card ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      <p>{detail}</p>
    </article>
  );
}

type SummaryQueryResult<T> = {
  data?: { data: T };
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
  refetch: () => unknown;
};

type TimelineQueryResult = {
  data?: { pages: Array<{ data: WatchlistHandleTimelineData }> };
  error: unknown;
  fetchNextPage: () => unknown;
  hasNextPage: boolean;
  isError: boolean;
  isFetching: boolean;
  isFetchingNextPage: boolean;
  isPending: boolean;
  refetch: () => unknown;
};

function HandleTopicSummary({ query }: { query: SummaryQueryResult<WatchlistHandleSummaryData> }) {
  if (query.isPending) {
    return <RemoteState.Loading label="Loading watchlist summary" layout="panel" rows={3} />;
  }
  if (query.isError) {
    return <RemoteState.Error error={query.error} onRetry={() => query.refetch()} />;
  }
  const summary = query.data?.data;
  if (!summary) {
    return <RemoteState.Empty title="No account topic summary." />;
  }
  const generatedAt = summary.generated_at_ms ? formatRelativeTime(summary.generated_at_ms) : null;
  const statusLabel =
    summary.status === "not_ready"
      ? summary.pending_recompute
        ? "pending"
        : "not ready"
      : summary.is_stale
        ? "stale"
        : generatedAt
          ? `${generatedAt} ago`
          : "ready";
  return (
    <section className="watchlist-summary-panel" aria-label="Handle topic summary">
      <div className="watchlist-summary-main">
        <div className="watchlist-summary-icon" aria-hidden>
          <Sparkles />
        </div>
        <div>
          <span className="watchlist-kicker">
            <TextSearch aria-hidden />
            account read
          </span>
          <p>
            {summary.summary_zh ||
              (summary.status === "not_ready"
                ? "近窗口内还没有生成账号主题汇总。"
                : "近窗口内还没有足够的结构化信号，暂不生成账号主题判断。")}
          </p>
        </div>
      </div>
      <div className="watchlist-summary-meta" aria-label="Summary status">
        <span>
          <Clock3 aria-hidden />
          {statusLabel}
        </span>
        <span>{summary.signal_count} signals</span>
        <span>{summary.input_event_count} inputs</span>
      </div>
      <div className="watchlist-topic-strip">
        {summary.topics.length ? (
          summary.topics.slice(0, 5).map((topic) => (
            <article className="watchlist-topic-pill" key={topic.title}>
              <b>{topic.title}</b>
              <span>{topic.event_count ?? 0} signals</span>
              {topic.description ? <p>{topic.description}</p> : null}
            </article>
          ))
        ) : (
          <span className="watchlist-summary-empty">topic queue warming</span>
        )}
      </div>
    </section>
  );
}

function HandleTimeline({
  onScopeChange,
  query,
  scope,
}: {
  onScopeChange: (scope: WatchlistTimelineScope) => void;
  query: TimelineQueryResult;
  scope: WatchlistTimelineScope;
}) {
  if (query.isPending) {
    return <RemoteState.Loading label="Loading handle timeline" layout="panel" rows={6} />;
  }
  if (query.isError) {
    return <RemoteState.Error error={query.error} onRetry={() => query.refetch()} />;
  }
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.data.items);
  return (
    <RemoteState.Stale updating={query.isFetching}>
      <div className="watchlist-scope-tabs" role="tablist" aria-label="Timeline scope">
        <button
          aria-selected={scope === "signal"}
          className={scope === "signal" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => onScopeChange("signal")}
        >
          signal
        </button>
        <button
          aria-selected={scope === "all"}
          className={scope === "all" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => onScopeChange("all")}
        >
          all
        </button>
      </div>
      {items.length ? (
        <ol className="watchlist-evidence-stream">
          {items.map((item) => (
            <HandleTimelineItem item={item} key={item.event_id} />
          ))}
        </ol>
      ) : (
        <RemoteState.Empty
          action={
            scope === "signal" ? (
              <button
                className="watchlist-inline-command"
                type="button"
                onClick={() => onScopeChange("all")}
              >
                Show all
              </button>
            ) : null
          }
          title={scope === "signal" ? "No signal events yet." : "No source events yet."}
        />
      )}
      {query.hasNextPage ? (
        <div className="watchlist-load-more-row">
          <button
            className="watchlist-load-more"
            disabled={query.isFetchingNextPage}
            type="button"
            onClick={() => void query.fetchNextPage()}
          >
            <ChevronDown aria-hidden />
            {query.isFetchingNextPage ? "Loading" : "Load more"}
          </button>
        </div>
      ) : null}
    </RemoteState.Stale>
  );
}

function HandleTimelineItem({ item }: { item: WatchlistTimelineItem }) {
  const social = item.social_event;
  const summary = social?.summary_zh;
  const anchorTerms = termsFromRecords(social?.anchor_terms, "term");
  const tokenSymbols = termsFromRecords(social?.token_candidates, "symbol");
  const pills = [
    social?.event_type,
    social?.subject,
    ...tokenSymbols.map((value) => `$${value.replace(/^\$+/, "")}`),
    ...(item.cashtags?.map((value) => `$${value.replace(/^\$+/, "")}`) ?? []),
    ...(item.hashtags?.map((value) => `#${value.replace(/^#+/, "")}`) ?? []),
  ]
    .filter(Boolean)
    .slice(0, 8) as string[];

  return (
    <li>
      <div className="watchlist-evidence-time">
        <span>
          {item.received_at_ms ? `${formatRelativeTime(item.received_at_ms)} ago` : "no timestamp"}
        </span>
      </div>
      <article className={`watchlist-evidence-card ${summary ? "signal" : "source"}`}>
        <div>
          {item.canonical_url ? (
            <a href={item.canonical_url} rel="noreferrer" target="_blank">
              @{item.author_handle ?? "source"}
            </a>
          ) : (
            <b>@{item.author_handle ?? "source"}</b>
          )}
          <ObsidianPill tone={summary ? "opportunity" : "health"}>
            {summary ? "signal" : "source"}
          </ObsidianPill>
        </div>
        {summary ? <p className="watchlist-signal-summary">{summary}</p> : null}
        {pills.length ? (
          <div className="watchlist-evidence-pills">
            {pills.map((pill) => (
              <span key={pill}>{pill}</span>
            ))}
          </div>
        ) : null}
        {anchorTerms.length ? (
          <div className="watchlist-anchor-row">
            {anchorTerms.slice(0, 5).map((term) => (
              <span key={term}>{term}</span>
            ))}
          </div>
        ) : null}
        {item.text_clean ? (
          <details className="watchlist-original-text">
            <summary>Original</summary>
            <p>{item.text_clean}</p>
          </details>
        ) : null}
      </article>
    </li>
  );
}

function termsFromRecords(
  records: Array<Record<string, unknown>> | undefined,
  key: string,
): string[] {
  return [
    ...new Set(
      (records ?? [])
        .map((item) => {
          const value = item[key];
          return typeof value === "string" ? value : "";
        })
        .filter(Boolean),
    ),
  ];
}

function timelineLeadCopy(scope: WatchlistTimelineScope, count: number): string {
  if (count > 0) {
    return scope === "signal" ? `${count} structured signals` : `${count} source events`;
  }
  return scope === "signal" ? "Structured social-event output." : "Raw source stream.";
}

function ClusterPanel({
  emptyLabel,
  eyebrow,
  items,
  title,
}: {
  emptyLabel: string;
  eyebrow: string;
  items: WatchlistAccountCase["tokenMentions"];
  title: string;
}) {
  return (
    <section className="watchlist-cluster-panel" aria-labelledby={`watchlist-${slug(title)}`}>
      <div className="watchlist-section-head">
        <span>{eyebrow}</span>
        <h3 id={`watchlist-${slug(title)}`}>{title}</h3>
      </div>
      <ClusterList emptyLabel={emptyLabel} items={items} />
    </section>
  );
}

function ClusterList({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: WatchlistAccountCase["tokenMentions"];
}) {
  if (!items.length) {
    return <RemoteState.Empty title={emptyLabel} />;
  }

  return (
    <ul className="watchlist-cluster-list">
      {items.map((item) => (
        <li key={item.label}>
          <Link to={searchPath({ q: item.query })}>
            <b>{item.label}</b>
            <span>
              {item.count} event{item.count === 1 ? "" : "s"}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RiskPanel({ notes }: { notes: string[] }) {
  return (
    <section className="watchlist-cluster-panel" aria-labelledby="watchlist-risk-notes">
      <div className="watchlist-section-head">
        <span>data quality</span>
        <h3 id="watchlist-risk-notes">Risk notes</h3>
      </div>
      {notes.length ? (
        <ul className="watchlist-risk-list">
          {notes.map((note, index) => (
            <li key={`${note}-${index}`}>{note}</li>
          ))}
        </ul>
      ) : (
        <RemoteState.Empty title="No account-level risk notes in this window." />
      )}
    </section>
  );
}

function emptyAccountCase(handle: string): WatchlistAccountCase {
  return {
    emptyState: "No source events in this window.",
    handle,
    lastSeenAtMs: null,
    narrativeClusters: [],
    recentEvents: [],
    riskNotes: [],
    searchLinks: [
      {
        href: searchPath({ q: `@${handle}` }),
        label: "Search account",
      },
    ],
    tokenMentions: [],
    unreadCount: 0,
  };
}

function lastSeenCopy(value: number | null): string {
  return value ? `Last source event ${formatRelativeTime(value)} ago` : "No recent source event";
}

function topClusterCopy(items: WatchlistAccountCase["tokenMentions"]): string {
  const [top] = items;
  return top ? `lead ${top.label} · ${top.count} event${top.count === 1 ? "" : "s"}` : "none yet";
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
