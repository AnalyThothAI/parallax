import { getApi } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import type { MacroSeriesData } from "../model/macroTypes";

export function useMacroSeriesQuery({
  conceptKeys,
  token,
  window = "60d",
}: {
  conceptKeys: string[];
  token: string;
  window?: "20d" | "60d" | "120d" | "1y" | "3y";
}) {
  const normalizedConceptKeys = conceptKeys.map((key) => key.trim()).filter(Boolean);

  return useQuery({
    queryKey: queryKeys.macroSeries(normalizedConceptKeys, window),
    queryFn: async () => {
      const response = await getApi<MacroSeriesData>("/api/macro/series", {
        params: {
          concept_keys: normalizedConceptKeys.join(","),
          window,
        },
        token,
      });
      return response.data;
    },
    enabled: Boolean(token) && normalizedConceptKeys.length > 0,
    refetchInterval: 60_000,
  });
}
