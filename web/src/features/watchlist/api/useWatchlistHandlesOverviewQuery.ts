import { getApi } from "@lib/api/client";
import type { WatchlistHandlesOverviewData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useWatchlistHandlesOverviewQuery({ token }: { token: string }) {
  return useQuery({
    queryKey: queryKeys.watchlistHandlesOverview(),
    queryFn: () =>
      getApi<WatchlistHandlesOverviewData>("/api/watchlist/handles/overview", { token }),
    enabled: Boolean(token),
    refetchInterval: 15_000,
  });
}
