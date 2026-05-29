import { getApi } from "@lib/api/client";
import type { AssetFlowData, ScopeKey, WindowKey } from "@lib/types";
import type { TokenRadarVenueFilter } from "@lib/venue";
import { queryKeys } from "@shared/query/queryKeys";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

export function useTokenRadarQuery({
  token,
  window,
  scope,
  venue,
  limit = 48,
  enabled = true,
}: {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  venue: TokenRadarVenueFilter;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.tokenRadar(window, scope, venue, limit),
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window, limit, scope, venue },
      }),
    enabled: Boolean(token) && enabled,
    refetchInterval: 10_000,
    placeholderData: keepPreviousData,
  });
}
