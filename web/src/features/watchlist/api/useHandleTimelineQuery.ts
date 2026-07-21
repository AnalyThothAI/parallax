import { getApi } from "@lib/api/client";
import type { WatchlistHandleTimelineData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery } from "@tanstack/react-query";

export function useHandleTimelineQuery({
  handle,
  limit = 80,
  token,
}: {
  handle: string | null;
  limit?: number;
  token: string;
}) {
  return useInfiniteQuery({
    queryKey: queryKeys.watchlistHandleTimeline(handle ?? "", limit),
    queryFn: ({ pageParam }) =>
      getApi<WatchlistHandleTimelineData>(
        `/api/watchlist/handle/${encodeURIComponent(handle ?? "")}/timeline`,
        {
          token,
          params: { cursor: pageParam || undefined, limit },
        },
      ),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.data.next_cursor || undefined,
    enabled: Boolean(token && handle),
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 0) > 1 ? false : 15_000),
  });
}
