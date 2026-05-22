import { getApi } from "@lib/api/client";
import type { MacroModuleView } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

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
      const response = await getApi<MacroModuleView>(`/api/macro/modules/${moduleId}`, { token });
      return response.data;
    },
    enabled: Boolean(token),
    refetchInterval: 60_000,
  });
}
