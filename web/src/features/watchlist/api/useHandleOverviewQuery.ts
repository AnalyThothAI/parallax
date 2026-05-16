import { getApi } from "@lib/api/client";
import type { WatchlistHandleOverviewData, WatchlistTimelineScope } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useHandleOverviewQuery({
  handle,
  scope,
  token,
}: {
  handle: string | null;
  scope: WatchlistTimelineScope;
  token: string;
}) {
  return useQuery({
    queryKey: queryKeys.watchlistHandleOverview(handle ?? "", scope),
    queryFn: () =>
      getApi<WatchlistHandleOverviewData>(
        `/api/watchlist/handle/${encodeURIComponent(handle ?? "")}/overview`,
        {
          token,
          params: { scope },
        },
      ),
    enabled: Boolean(token && handle),
    refetchInterval: 15_000,
  });
}
