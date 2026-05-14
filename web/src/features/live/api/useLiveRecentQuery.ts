import { getApi } from "@lib/api/client";
import type { RecentData, ScopeKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useLiveRecentQuery({
  handles,
  scope,
  token,
}: {
  handles: string;
  scope: ScopeKey;
  token: string;
}) {
  return useQuery({
    queryKey: queryKeys.liveRecent(scope, handles),
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: { limit: 80, scope, handles },
      }),
    enabled: Boolean(token),
    refetchInterval: 15_000,
  });
}
