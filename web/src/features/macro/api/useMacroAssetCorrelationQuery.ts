import { getApi } from "@lib/api/client";
import type { MacroAssetCorrelationData, MacroAssetCorrelationWindow } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

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
      const response = await getApi<MacroAssetCorrelationData>(
        "/api/macro/assets/correlation",
        {
          params: { window },
          token,
        },
      );
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
