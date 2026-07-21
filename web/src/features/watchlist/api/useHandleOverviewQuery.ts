import { getApi } from "@lib/api/client";
import type { WatchlistHandleOverviewData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useHandleOverviewQuery({
  handle,
  token,
}: {
  handle: string | null;
  token: string;
}) {
  return useQuery({
    queryKey: queryKeys.watchlistHandleOverview(handle ?? ""),
    queryFn: () =>
      getApi<WatchlistHandleOverviewData>(
        `/api/watchlist/handle/${encodeURIComponent(handle ?? "")}/overview`,
        { token },
      ),
    enabled: Boolean(token && handle),
    refetchInterval: 15_000,
  });
}
