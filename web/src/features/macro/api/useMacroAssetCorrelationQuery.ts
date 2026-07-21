import { getApi } from "@lib/api/client";
import type { MacroAssetCorrelationWindow } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import { requireMacroAssetCorrelationData } from "../model/macroCurrentContract";

export function useMacroAssetCorrelationQuery({
  token,
  window,
}: {
  token: string;
  window: MacroAssetCorrelationWindow;
}) {
  return useQuery({
    queryKey: queryKeys.macroAssetCorrelation(window),
    queryFn: async () => {
      const response = await getApi<unknown>("/api/macro/assets/correlation", {
        params: { window },
        token,
      });
      return requireMacroAssetCorrelationData(response.data);
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
