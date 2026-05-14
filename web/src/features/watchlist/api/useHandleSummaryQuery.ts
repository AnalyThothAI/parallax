import { getApi } from "@lib/api/client";
import type { WatchlistHandleSummaryData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useHandleSummaryQuery({ handle, token }: { handle: string | null; token: string }) {
  return useQuery({
    queryKey: queryKeys.watchlistHandleSummary(handle ?? ""),
    queryFn: () =>
      getApi<WatchlistHandleSummaryData>(
        `/api/watchlist/handle/${encodeURIComponent(handle ?? "")}/summary`,
        {
          token,
        },
      ),
    enabled: Boolean(token && handle),
    refetchInterval: 30_000,
  });
}
