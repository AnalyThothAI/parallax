import type { SearchItem } from "@lib/types";
import { useMemo } from "react";

import { buildTopicBuckets } from "../model/searchTopicTimeline";

export function SearchTopicTimeline({ items }: { items: SearchItem[] }) {
  const buckets = useMemo(() => buildTopicBuckets(items), [items]);
  const peak = Math.max(...buckets.map((bucket) => bucket.posts), 1);

  return (
    <section className="search-panel search-topic-timeline" id="timeline">
      <header>
        <h3>Topic Mention Timeline</h3>
        <span>{buckets.length} buckets</span>
      </header>
      <div className="search-topic-bars" aria-label="topic buckets">
        {buckets.map((bucket) => (
          <div key={bucket.startMs}>
            <i style={{ height: `${Math.max(8, (bucket.posts / peak) * 100)}%` }} />
            <span>{bucket.posts}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
