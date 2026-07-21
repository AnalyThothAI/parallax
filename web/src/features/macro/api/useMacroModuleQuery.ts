import { getApi } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import { requireMacroModuleView } from "../model/macroCurrentContract";
import type { MacroModuleId } from "../model/macroRoutes";

export function useMacroModuleQuery({
  moduleId = "overview",
  token,
}: {
  moduleId?: MacroModuleId;
  token: string;
}) {
  return useQuery({
    queryKey: queryKeys.macroModule(moduleId),
    queryFn: async () => {
      const response = await getApi<unknown>(`/api/macro/modules/${moduleId}`, { token });
      return requireMacroModuleView(response.data);
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
