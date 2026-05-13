import { useQuery } from "@tanstack/react-query";

import { getApi } from "./client";
import type { AssetFlowData, ScopeKey, WindowKey } from "./types";

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
    queryKey: ["token-radar", window, scope],
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window, limit, scope },
      }),
    enabled: Boolean(token) && enabled,
    refetchInterval: 10_000,
  });
}
