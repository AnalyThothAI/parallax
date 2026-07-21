import type { WatchlistHandleTimelineData } from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { ChevronDown } from "lucide-react";

import { HandleTimelineItem } from "./HandleTimelineItem";

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

export function HandleTimeline({ query }: { query: TimelineQueryResult }) {
  if (query.isPending) {
    return <PageState.Loading label="Loading handle timeline" layout="panel" rows={6} />;
  }
  if (query.isError) {
    return <PageState.Error error={query.error} onRetry={() => query.refetch()} />;
  }
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.data.items);
  return (
    <PageState.Stale updating={query.isFetching}>
      {items.length ? (
        <ol className="watchlist-evidence-stream">
          {items.map((item) => (
            <HandleTimelineItem item={item} key={item.event_id} />
          ))}
        </ol>
      ) : (
        <PageState.Empty title="No source events yet." />
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
    </PageState.Stale>
  );
}
