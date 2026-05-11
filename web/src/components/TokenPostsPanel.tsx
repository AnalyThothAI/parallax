import { ExternalLink } from "lucide-react";
import type { TokenPostItem, TokenPostRange, TokenPostSortMode, TokenPostsData } from "../api/types";
import { compactNumber, eventText, formatReason, formatRelativeTime, formatRisk, formatScore, formatSignedPercent } from "../lib/format";
import { SkeletonRows } from "../shared/ui/RemoteState";

type TokenPostsPanelProps = {
  posts?: TokenPostsData | null;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  selectedStageId?: string | null;
  onPostRangeChange: (range: TokenPostRange) => void;
  onPostSortModeChange: (mode: TokenPostSortMode) => void;
  onHideDuplicateClustersChange: (enabled: boolean) => void;
  onWatchedPostsOnlyChange: (enabled: boolean) => void;
  onLoadMorePosts: () => void;
};

export function TokenPostsPanel({
  posts,
  isLoading,
  isFetchingNextPage,
  postRange,
  postSortMode,
  hideDuplicateClusters,
  watchedPostsOnly,
  selectedStageId,
  onPostRangeChange,
  onPostSortModeChange,
  onHideDuplicateClustersChange,
  onWatchedPostsOnlyChange,
  onLoadMorePosts
}: TokenPostsPanelProps) {
  const allItems = posts?.items ?? [];
  const items = sortPosts(
    allItems.filter((item) => {
      if (selectedStageId && item.stage_id !== selectedStageId) {
        return false;
      }
      if (watchedPostsOnly && !item.is_watched) {
        return false;
      }
      if (hideDuplicateClusters && item.post_quality.risks.some((risk) => risk.includes("duplicate") || risk.includes("repeated"))) {
        return false;
      }
      return true;
    }),
    postSortMode
  );
  return (
    <div className="token-posts-panel">
      <header className="posts-toolbar">
        <div className="segmented mini range" aria-label="token post range">
          <button className={postRange === "current_window" ? "active" : ""} type="button" onClick={() => onPostRangeChange("current_window")}>
            window
          </button>
          <button className={postRange === "since_ignition" ? "active" : ""} type="button" onClick={() => onPostRangeChange("since_ignition")}>
            ignition
          </button>
          <button className={postRange === "all_history" ? "active" : ""} type="button" onClick={() => onPostRangeChange("all_history")}>
            history
          </button>
        </div>
        <div className="segmented mini post-sort" aria-label="token post sort">
          <button className={postSortMode === "recent" ? "active" : ""} type="button" onClick={() => onPostSortModeChange("recent")}>
            recent
          </button>
          <button className={postSortMode === "catalyst" ? "active" : ""} type="button" onClick={() => onPostSortModeChange("catalyst")}>
            catalyst
          </button>
          <button className={postSortMode === "quality" ? "active" : ""} type="button" onClick={() => onPostSortModeChange("quality")}>
            quality
          </button>
        </div>
        <label>
          <input
            checked={watchedPostsOnly}
            onChange={(event) => onWatchedPostsOnlyChange(event.target.checked)}
            type="checkbox"
          />
          watched
        </label>
        <label>
          <input
            checked={hideDuplicateClusters}
            onChange={(event) => onHideDuplicateClustersChange(event.target.checked)}
            type="checkbox"
          />
          hide duplicates
        </label>
      </header>

      <div className="posts-count-line">
        {posts ? `${posts.total_count} total · ${posts.returned_count} loaded · score window ${posts.score_window.window}` : "0 total · 0 loaded"}
      </div>
      {selectedStageId ? <div className="filter-note">stage filter · {selectedStageId}</div> : null}
      {postRange === "all_history" ? <div className="filter-note">history does not all participate in current score</div> : null}
      {hideDuplicateClusters ? <div className="filter-note">已隐藏重复文本簇</div> : null}
      {isLoading ? <SkeletonRows count={4} label="loading token posts" /> : null}
      {!isLoading && items.length === 0 ? <div className="empty-state">该窗口暂无 token-attributed posts</div> : null}
      <div className="post-list">
        {items.map((item) => (
          <PostCard key={item.event_id} item={item} />
        ))}
      </div>
      {posts?.has_more ? (
        <button className="load-more-posts" type="button" onClick={onLoadMorePosts} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? "加载中" : "加载更多"}
        </button>
      ) : null}
    </div>
  );
}

function PostCard({ item }: { item: TokenPostItem }) {
  const topReason = item.post_quality.reasons[0] ?? item.post_quality.risks[0];
  return (
    <article className="post-card">
      <div>
        <strong>@{item.handle ?? "unknown"}</strong>
        <span>{formatScore(item.post_quality.score)}</span>
        <em>{topReason ? formatReason(topReason) : "post quality"}</em>
        {item.stage_phase ? <i>{item.stage_phase}</i> : null}
        {item.author_role ? <i>{item.author_role}</i> : null}
        {item.is_stage_representative ? <i className="catalyst-chip">representative</i> : null}
        {item.catalyst_score !== null && item.catalyst_score !== undefined ? <i className="catalyst-chip">cat {formatScore(item.catalyst_score)}</i> : null}
        {item.price ? <i>{item.price.status === "ready" && item.price.price_usd ? `$${compactNumber(item.price.price_usd)}` : item.price.status}</i> : null}
        {item.price_delta_from_previous_post_pct !== null && item.price_delta_from_previous_post_pct !== undefined ? (
          <i>{formatSignedPercent(item.price_delta_from_previous_post_pct)} prev</i>
        ) : null}
        {item.post_quality.risks.slice(0, 2).map((risk) => (
          <i key={risk}>{formatRisk(risk)}</i>
        ))}
        <time>{formatRelativeTime(item.received_at_ms)}</time>
        {item.url ? (
          <a href={item.url} target="_blank" rel="noreferrer" aria-label="打开原文">
            <ExternalLink aria-hidden />
          </a>
        ) : null}
      </div>
      <p>{eventText({ event_id: item.event_id, text_clean: item.text })}</p>
      {item.catalyst_components ? (
        <div className="catalyst-components">
          <span>{formatScore(item.catalyst_components.followup_count)} followups</span>
          <span>{formatScore(item.catalyst_components.independent_authors)} authors</span>
          <span>{formatScore(item.catalyst_components.explicit_cascade_followups)} refs</span>
        </div>
      ) : null}
    </article>
  );
}

function sortPosts(items: TokenPostItem[], mode: TokenPostSortMode): TokenPostItem[] {
  const copy = [...items];
  if (mode === "catalyst") {
    return copy.sort((a, b) => Number(b.catalyst_score ?? 0) - Number(a.catalyst_score ?? 0));
  }
  if (mode === "quality") {
    return copy.sort((a, b) => b.post_quality.score - a.post_quality.score);
  }
  return copy.sort((a, b) => Number(b.received_at_ms ?? 0) - Number(a.received_at_ms ?? 0));
}
