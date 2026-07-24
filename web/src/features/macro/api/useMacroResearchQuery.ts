import { getApi } from "@lib/api/client";
import { useQuery } from "@tanstack/react-query";

import type { MacroResearchReadData } from "../model/macroTypes";

export function useMacroResearchQuery({
  sessionDate,
  token,
}: {
  sessionDate: string | null;
  token: string;
}) {
  return useQuery({
    queryKey: ["macro", "research", sessionDate ?? "latest"] as const,
    queryFn: async () => {
      const response = await getApi<MacroResearchReadData>("/api/macro/research", {
        token,
        params: { session_date: sessionDate },
      });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
