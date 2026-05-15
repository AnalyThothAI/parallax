import type { TokenCaseSort, TokenCaseViewModel } from "@shared/model/tokenCaseViewModel";

import { TokenCasePostEventCard } from "./TokenCasePostEventCard";
import styles from "./TokenCaseTimeline.module.css";

type TokenCaseTimelineProps = {
  timeline: TokenCaseViewModel["timeline"];
  onTimelineSortChange: (sort: TokenCaseSort) => void;
  onLoadMorePosts: () => void;
};

const SORTS: Array<{ key: TokenCaseSort; label: string }> = [
  { key: "catalyst", label: "Catalyst" },
  { key: "recent", label: "Recent" },
  { key: "watched", label: "Watched" },
];

export function TokenCaseTimeline({
  timeline,
  onTimelineSortChange,
  onLoadMorePosts,
}: TokenCaseTimelineProps) {
  return (
    <section className={styles.timeline} aria-labelledby="token-case-timeline">
      <header className={styles.header}>
        <div>
          <span>Mention stream</span>
          <h2 id="token-case-timeline">Mention Timeline</h2>
        </div>
        <div className={styles.toolbar} role="group" aria-label="timeline sort">
          {SORTS.map((sort) => (
            <button
              key={sort.key}
              type="button"
              aria-pressed={timeline.sort === sort.key}
              onClick={() => onTimelineSortChange(sort.key)}
            >
              {sort.label}
            </button>
          ))}
        </div>
      </header>
      <div className={styles.events}>
        {timeline.items.map((item) => (
          <TokenCasePostEventCard key={item.id} item={item} />
        ))}
      </div>
      {timeline.emptyLabel ? <p className={styles.empty}>{timeline.emptyLabel}</p> : null}
      {timeline.hasMore ? (
        <button
          className={styles.loadMore}
          type="button"
          disabled={timeline.isLoading || timeline.isFetchingNextPage}
          onClick={onLoadMorePosts}
        >
          {timeline.isFetchingNextPage ? "Loading" : "Load more"}
        </button>
      ) : null}
    </section>
  );
}
