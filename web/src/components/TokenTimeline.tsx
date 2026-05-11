import type { TokenSocialTimelineData } from "../api/types";
import {
  compactNumber,
  formatPercentShare,
  formatPropagationPhase,
  formatRisk,
  formatScore,
} from "../lib/format";

type TokenTimelineProps = {
  timeline?: TokenSocialTimelineData | null;
  isLoading: boolean;
  selectedBucketStartMs?: number | null;
  onBucketSelect?: (bucketStartMs: number) => void;
};

export function TokenTimeline({
  timeline,
  isLoading,
  selectedBucketStartMs,
  onBucketSelect,
}: TokenTimelineProps) {
  if (isLoading) {
    return <TimelineSkeleton />;
  }
  if (!timeline) {
    return <div className="empty-state">该窗口暂无传播时间线</div>;
  }
  const maxPosts = Math.max(1, ...timeline.buckets.map((item) => item.posts));
  const sparse = timeline.summary.posts > 0 && timeline.summary.posts < 3;
  return (
    <div className="token-timeline">
      <header className="timeline-summary">
        <div>
          <span>传播相位</span>
          <b>{formatPropagationPhase(timeline.summary.phase)}</b>
        </div>
        <div>
          <span>Posts</span>
          <b>{compactNumber(timeline.summary.posts)}</b>
        </div>
        <div>
          <span>Authors</span>
          <b>{compactNumber(timeline.summary.authors)}</b>
        </div>
        <div>
          <span>Top Share</span>
          <b>{formatPercentShare(timeline.summary.top_author_share)}</b>
        </div>
        <div>
          <span>Repro</span>
          <b>
            {timeline.summary.reproduction_rate === null ||
            timeline.summary.reproduction_rate === undefined
              ? "-"
              : timeline.summary.reproduction_rate.toFixed(2)}
          </b>
        </div>
      </header>

      <div className="timeline-controls">
        <span className="muted-pill">auto bucket {timeline.query.bucket}</span>
        {sparse ? (
          <span className="risk-pill">{formatRisk("insufficient_timeline_data")}</span>
        ) : null}
        {timeline.buckets.every((item) => item.price?.status !== "ready") ? (
          <span className="muted-pill">pending_observation</span>
        ) : null}
      </div>

      <section className="timeline-chart" aria-label="social heat timeline">
        {timeline.buckets.length ? (
          timeline.buckets.map((item) => {
            const content = (
              <>
                <span
                  className="bucket-bar"
                  style={{ height: `${Math.max(8, (item.posts / maxPosts) * 88)}%` }}
                  aria-label={`${item.posts} posts`}
                />
                {item.watched_posts ? (
                  <i style={{ height: `${Math.max(8, (item.watched_posts / maxPosts) * 88)}%` }} />
                ) : null}
                {item.new_authors ? (
                  <strong
                    style={{ height: `${Math.max(8, (item.new_authors / maxPosts) * 88)}%` }}
                  />
                ) : null}
                {item.price_change_from_start_pct !== null &&
                item.price_change_from_start_pct !== undefined ? (
                  <em className={item.price_change_from_start_pct >= 0 ? "up" : "down"} />
                ) : null}
              </>
            );
            const className = `timeline-bucket ${selectedBucketStartMs === item.start_ms ? "selected" : ""}`;
            if (!onBucketSelect) {
              return (
                <span
                  className={className}
                  key={item.start_ms}
                  title={`${item.posts} posts / ${item.new_authors} new authors`}
                >
                  {content}
                </span>
              );
            }
            return (
              <button
                aria-label={`open replay bucket ${item.start_ms} ${item.posts} posts`}
                className={className}
                key={item.start_ms}
                title={`${item.posts} posts / ${item.new_authors} new authors`}
                type="button"
                onClick={() => onBucketSelect(item.start_ms)}
              >
                {content}
              </button>
            );
          })
        ) : (
          <div className="empty-state">该窗口暂无传播时间线</div>
        )}
      </section>

      <section className="author-lanes">
        {timeline.authors.slice(0, 8).map((author) => (
          <div className={`author-lane role-${author.role ?? "unknown"}`} key={author.handle}>
            <b>@{author.handle}</b>
            <span>{author.role ?? "author"}</span>
            <em>{compactNumber(author.posts)} posts</em>
            {author.quality_score !== null && author.quality_score !== undefined ? (
              <strong>{formatScore(author.quality_score)}</strong>
            ) : null}
          </div>
        ))}
        {timeline.authors.length === 0 ? <div className="empty-state">暂无作者 lane</div> : null}
      </section>
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="timeline-skeleton" aria-label="loading timeline">
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}
