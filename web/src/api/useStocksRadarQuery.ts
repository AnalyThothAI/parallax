import { useQuery } from "@tanstack/react-query";

import { getApi } from "./client";
import type { ScopeKey, StocksRadarData, WindowKey } from "./types";

type StocksRadarArgs = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  limit?: number;
};

export function useStocksRadarQuery({ token, window, scope, limit = 48 }: StocksRadarArgs) {
  return useQuery({
    queryKey: ["stocks-radar", window, scope, limit],
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
