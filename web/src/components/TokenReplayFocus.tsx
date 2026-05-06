import { ArrowLeft, ExternalLink } from "lucide-react";
import type { TokenSocialTimelineData, TokenTimelinePost } from "../api/types";
import { eventText, formatRelativeTime, formatRisk, formatScore } from "../lib/format";

type TokenReplayFocusProps = {
  timeline?: TokenSocialTimelineData | null;
  isLoading: boolean;
  selectedBucketStartMs: number | null;
  selectedEventId: string | null;
  onBack: () => void;
  onSelectedEventChange: (eventId: string | null) => void;
};

export function TokenReplayFocus({
  timeline,
  isLoading,
  selectedBucketStartMs,
  selectedEventId,
  onBack,
  onSelectedEventChange
}: TokenReplayFocusProps) {
  if (isLoading) {
    return <div className="empty-state">加载 replay 中</div>;
  }
  if (!timeline) {
    return <div className="empty-state">该窗口暂无传播复盘</div>;
  }

  const selectedBucket = timeline.buckets.find((item) => item.start_ms === selectedBucketStartMs) ?? timeline.buckets[0] ?? null;
  const bucketStartMs = selectedBucket?.start_ms ?? selectedBucketStartMs;
  const bucketPosts = timeline.posts
    .filter((post) => bucketStartMs === null || bucketStartMs === undefined || post.bucket_start_ms === bucketStartMs)
    .sort((a, b) => Number(a.received_at_ms ?? 0) - Number(b.received_at_ms ?? 0));
  const replayPosts = bucketPosts.length ? bucketPosts : [...timeline.posts].sort((a, b) => Number(a.received_at_ms ?? 0) - Number(b.received_at_ms ?? 0));
  const selectedPost = replayPosts.find((post) => post.event_id === selectedEventId) ?? replayPosts[0] ?? null;
  const cascadeEdges = timeline.cascade.edges.filter(
    (edge) => edge.event_id === selectedPost?.event_id || edge.parent_event_id === selectedPost?.event_id
  );

  return (
    <div className="replay-focus">
      <header className="replay-focus-head">
        <button className="ghost-icon-button" type="button" onClick={onBack} aria-label="Back to timeline">
          <ArrowLeft aria-hidden />
          <span>Back to timeline</span>
        </button>
        <div>
          <div className="section-title">Replay Focus</div>
          <p>{bucketSummary(selectedBucket, replayPosts.length)}</p>
        </div>
      </header>

      <div className="replay-focus-grid">
        <section className="replay-event-rail" aria-label="bucket replay events">
          {replayPosts.map((post, index) => (
            <button
              className={post.event_id === selectedPost?.event_id ? "active" : ""}
              key={post.event_id}
              type="button"
              onClick={() => onSelectedEventChange(post.event_id)}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <b>@{post.handle ?? "unknown"}</b>
              <em>{formatRelativeTime(post.received_at_ms)}</em>
              <p>{postText(post)}</p>
              <ReplayChips post={post} />
            </button>
          ))}
          {!replayPosts.length ? <div className="empty-state">该 bucket 暂无帖子</div> : null}
        </section>

        <aside className="replay-inspector">
          {selectedPost ? (
            <>
              <div className="replay-inspector-title">
                <strong>@{selectedPost.handle ?? "unknown"}</strong>
                <span>{formatScore(selectedPost.post_quality.score)}</span>
              </div>
              <p>{postText(selectedPost)}</p>
              <div className="replay-chip-row">
                {selectedPost.event_type ? <span>{selectedPost.event_type}</span> : null}
                {selectedPost.is_first_seen_by_watched_for_token ? <span>first watched evidence</span> : null}
                {selectedPost.reference?.type ? <span>{selectedPost.reference.type}</span> : null}
                {selectedPost.reference?.author_handle ? <span>@{selectedPost.reference.author_handle}</span> : null}
              </div>
              {selectedPost.url ? (
                <a className="replay-link" href={selectedPost.url} rel="noreferrer" target="_blank">
                  source <ExternalLink aria-hidden />
                </a>
              ) : null}
              <dl className="replay-metrics">
                <div>
                  <dt>quality</dt>
                  <dd>{formatScore(selectedPost.post_quality.score)}</dd>
                </div>
                <div>
                  <dt>cascade edges</dt>
                  <dd>{cascadeEdges.length}</dd>
                </div>
                <div>
                  <dt>risk</dt>
                  <dd>{formatRisk(selectedPost.post_quality.risks[0])}</dd>
                </div>
              </dl>
              {cascadeEdges.length ? (
                <div className="replay-cascade-list">
                  {cascadeEdges.map((edge) => (
                    <span key={`${edge.event_id}-${edge.parent_event_id}-${edge.parent_tweet_id}`}>
                      {edge.resolved ? "linked" : "unresolved"} · {edge.edge_type ?? "referenced"} · {edge.parent_author_handle ? `@${edge.parent_author_handle}` : edge.parent_tweet_id}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty-state">该 bucket 暂无选中事件</div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ReplayChips({ post }: { post: TokenTimelinePost }) {
  const chips = [
    post.event_type,
    post.is_first_seen_by_watched_for_token ? "first watched" : null,
    post.reference?.type ? `${post.reference.type}` : null
  ].filter(Boolean);
  if (!chips.length) {
    return null;
  }
  return (
    <span className="replay-chip-row">
      {chips.map((chip) => (
        <i key={String(chip)}>{chip}</i>
      ))}
    </span>
  );
}

function bucketSummary(bucket: TokenSocialTimelineData["buckets"][number] | null, fallbackPosts: number): string {
  const posts = bucket?.posts ?? fallbackPosts;
  const newAuthors = bucket?.new_authors ?? 0;
  return `selected bucket · ${posts} ${plural(posts, "post")} · ${newAuthors} new ${plural(newAuthors, "author")}`;
}

function postText(post: TokenTimelinePost): string {
  return eventText({ event_id: post.event_id, text_clean: post.text }) || post.event_id;
}

function plural(value: number, noun: string): string {
  return value === 1 ? noun : `${noun}s`;
}
