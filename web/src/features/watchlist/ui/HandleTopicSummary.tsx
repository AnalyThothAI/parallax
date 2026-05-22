import { formatRelativeTime } from "@lib/format";
import type { WatchlistHandleSummaryData } from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Clock3, Sparkles, TextSearch } from "lucide-react";

type SummaryQueryResult<T> = {
  data?: { data: T };
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
  refetch: () => unknown;
};

export function HandleTopicSummary({
  query,
}: {
  query: SummaryQueryResult<WatchlistHandleSummaryData>;
}) {
  if (query.isPending) {
    return <PageState.Loading label="Loading watchlist summary" layout="panel" rows={3} />;
  }
  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => query.refetch()} />;
  }
  const summary = query.data?.data;
  if (!summary) {
    return <PageState.Empty title="No account topic summary." />;
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
