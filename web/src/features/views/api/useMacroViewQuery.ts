import { getApi } from "@lib/api/client";
import type { MacroViewsData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useMacroViewQuery({ token }: { token: string }) {
  return useQuery({
    queryKey: queryKeys.macroView(),
    queryFn: async () => {
      const response = await getApi<MacroViewsData>("/api/views/macro", { token });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
