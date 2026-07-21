import { getApi } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import { requireStatusData } from "../model/statusCurrentContract";

export function useCockpitStatusQuery({ token }: { token: string }) {
  return useQuery({
    queryKey: queryKeys.status(),
    queryFn: async () => {
      const response = await getApi<unknown>("/api/status", { token });
      return { ...response, data: requireStatusData(response.data) };
    },
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });
}
