import { ExternalLink } from "lucide-react";
import type { TimelineBucket, TokenSocialTimelineData } from "../api/types";
import {
  compactNumber,
  eventText,
  formatBucketLabel,
  formatPercentShare,
  formatPropagationPhase,
  formatRelativeTime,
  formatRisk,
  formatScore
} from "../lib/format";

type TokenTimelineProps = {
  timeline?: TokenSocialTimelineData | null;
  isLoading: boolean;
  bucket: TimelineBucket;
  onBucketChange: (bucket: TimelineBucket) => void;
};

const BUCKETS: TimelineBucket[] = ["30s", "1m", "5m"];

export function TokenTimeline({ timeline, isLoading, bucket, onBucketChange }: TokenTimelineProps) {
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
      </header>

      <div className="timeline-controls">
        {BUCKETS.map((item) => (
          <button key={item} className={bucket === item ? "active" : ""} type="button" onClick={() => onBucketChange(item)}>
            {formatBucketLabel(item)}
          </button>
        ))}
        {sparse ? <span className="risk-pill">{formatRisk("insufficient_timeline_data")}</span> : null}
        {timeline.buckets.every((item) => item.price == null) ? <span className="muted-pill">price snapshot missing</span> : null}
      </div>

      <section className="timeline-chart" aria-label="social heat timeline">
        {timeline.buckets.length ? (
          timeline.buckets.map((item) => (
            <div className="timeline-bucket" key={item.start_ms} title={`${item.posts} posts / ${item.new_authors} new authors`}>
              <span
                className="bucket-bar"
                style={{ height: `${Math.max(8, (item.posts / maxPosts) * 88)}%` }}
                aria-label={`${item.posts} posts`}
              />
              {item.watched_posts ? <i style={{ height: `${Math.max(8, (item.watched_posts / maxPosts) * 88)}%` }} /> : null}
              {item.price_change_from_start_pct !== null && item.price_change_from_start_pct !== undefined ? (
                <em className={item.price_change_from_start_pct >= 0 ? "up" : "down"} />
              ) : null}
            </div>
          ))
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
            {author.quality_score !== null && author.quality_score !== undefined ? <strong>{formatScore(author.quality_score)}</strong> : null}
          </div>
        ))}
        {timeline.authors.length === 0 ? <div className="empty-state">暂无作者 lane</div> : null}
      </section>

      <section className="timeline-post-list">
        {timeline.posts.slice(0, 12).map((post) => (
          <article className="timeline-post" key={post.event_id}>
            <div>
              <strong>@{post.handle ?? "unknown"}</strong>
              <span>{formatScore(post.post_quality.score)}</span>
              <time>{formatRelativeTime(post.received_at_ms)}</time>
              {post.url ? (
                <a href={post.url} target="_blank" rel="noreferrer" aria-label="打开原文">
                  <ExternalLink aria-hidden />
                </a>
              ) : null}
            </div>
            <p>{eventText({ event_id: post.event_id, text_clean: post.text })}</p>
          </article>
        ))}
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
