import type { ReactNode } from "react";

export type WatchlistMetrics = {
  source_event_count: number;
  resolved_token_count: number;
  candidate_mention_count: number;
  hashtag_count: number;
};

export function WatchlistMetricStrip({
  metrics,
  unreadCount,
}: {
  metrics: WatchlistMetrics | null;
  unreadCount: number;
}) {
  return (
    <section className="watchlist-signal-strip" aria-label="Monitor status">
      <SignalCard
        detail={unreadCount ? "notifications waiting" : "queue clear"}
        label="Unread"
        tone={unreadCount ? "opportunity" : "neutral"}
        value={unreadCount}
      />
      <SignalCard
        detail="persisted source stream"
        label="Source events"
        tone={metrics?.source_event_count ? "health" : "neutral"}
        value={metrics?.source_event_count ?? 0}
      />
      <SignalCard
        detail="resolved crypto targets"
        label="Resolved targets"
        tone={metrics?.resolved_token_count ? "info" : "neutral"}
        value={metrics?.resolved_token_count ?? 0}
      />
      <SignalCard
        detail="unresolved source mentions"
        label="Candidate mentions"
        tone={metrics?.candidate_mention_count ? "info" : "neutral"}
        value={metrics?.candidate_mention_count ?? 0}
      />
      <SignalCard
        detail="hashtags in source posts"
        label="Hashtags"
        tone={metrics?.hashtag_count ? "health" : "neutral"}
        value={metrics?.hashtag_count ?? 0}
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
  tone: "health" | "info" | "neutral" | "opportunity";
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
