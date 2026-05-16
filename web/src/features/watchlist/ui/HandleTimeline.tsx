import type { WatchlistHandleTimelineData, WatchlistTimelineScope } from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";
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

export function HandleTimeline({
  onScopeChange,
  query,
  scope,
}: {
  onScopeChange: (scope: WatchlistTimelineScope) => void;
  query: TimelineQueryResult;
  scope: WatchlistTimelineScope;
}) {
  if (query.isPending) {
    return <RemoteState.Loading label="Loading handle timeline" layout="panel" rows={6} />;
  }
  if (query.isError) {
    return <RemoteState.Error error={query.error} onRetry={() => query.refetch()} />;
  }
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.data.items);
  return (
    <RemoteState.Stale updating={query.isFetching}>
      <div className="watchlist-scope-tabs" role="tablist" aria-label="Timeline scope">
        <button
          aria-selected={scope === "signal"}
          className={scope === "signal" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => onScopeChange("signal")}
        >
          signal
        </button>
        <button
          aria-selected={scope === "all"}
          className={scope === "all" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => onScopeChange("all")}
        >
          all
        </button>
      </div>
      {items.length ? (
        <ol className="watchlist-evidence-stream">
          {items.map((item) => (
            <HandleTimelineItem item={item} key={item.event_id} />
          ))}
        </ol>
      ) : (
        <RemoteState.Empty
          action={
            scope === "signal" ? (
              <button
                className="watchlist-inline-command"
                type="button"
                onClick={() => onScopeChange("all")}
              >
                Show all
              </button>
            ) : null
          }
          title={scope === "signal" ? "No signal events yet." : "No source events yet."}
        />
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
    </RemoteState.Stale>
  );
}
