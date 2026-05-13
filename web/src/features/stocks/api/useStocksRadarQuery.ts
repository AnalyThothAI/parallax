
import { getApi } from "@lib/api/client";
import type { ScopeKey, StocksRadarData, WindowKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

type StocksRadarArgs = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  limit?: number;
};

export function useStocksRadarQuery({ token, window, scope, limit = 48 }: StocksRadarArgs) {
  return useQuery({
    queryKey: queryKeys.stocksRadar(window, scope, limit),
    queryFn: async () => {
      const response = await getApi<StocksRadarData>("/api/stocks-radar", {
        token,
        params: { window, scope, limit },
      });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 15_000,
  });
}
