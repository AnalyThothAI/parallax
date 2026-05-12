import type { TokenSocialTimelineData } from "../api/types";

type SearchTimelinePanelProps = {
  timeline: TokenSocialTimelineData;
};

export function SearchTimelinePanel({ timeline }: SearchTimelinePanelProps) {
  const peak = Math.max(...timeline.buckets.map((bucket) => bucket.posts), 1);
  return (
    <section className="search-panel search-timeline-panel">
      <header>
        <h3>24h Social x Market Timeline</h3>
        <span>price_series: anchor_line</span>
      </header>
      <div className="search-bucket-chart" aria-label="24h social buckets">
        {timeline.buckets.map((bucket) => (
          <div key={bucket.start_ms} className="search-bucket">
            <i style={{ height: `${Math.max(8, (bucket.posts / peak) * 100)}%` }} />
            <span>{bucket.posts}</span>
          </div>
        ))}
      </div>
      <div className="search-timeline-summary">
        <span>{timeline.summary.posts} posts</span>
        <span>{timeline.summary.authors} authors</span>
        <span>{timeline.summary.phase}</span>
        <span>top {Math.round(timeline.summary.top_author_share * 100)}%</span>
      </div>
    </section>
  );
}
