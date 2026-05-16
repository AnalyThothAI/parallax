import { getApi } from "@lib/api/client";
import type { AssetFlowData, ScopeKey, WindowKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

export function useTokenRadarQuery({
  token,
  window,
  scope,
  limit = 48,
  enabled = true,
}: {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.tokenRadar(window, scope, limit),
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window, limit, scope },
      }),
    enabled: Boolean(token) && enabled,
    refetchInterval: 10_000,
    placeholderData: keepPreviousData,
  });
}
