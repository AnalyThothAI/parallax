import { getApi } from "@lib/api/client";
import type { MacroData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export function useMacroQuery({ token }: { token: string }) {
  return useQuery({
    queryKey: queryKeys.macro(),
    queryFn: async () => {
      const response = await getApi<MacroData>("/api/macro", { token });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
