import { getApi } from "@lib/api/client";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type {
  MacroLiveEvidenceReadData,
  MacroLiveReadViewId,
  MacroLiveWindow,
} from "../model/macroTypes";

export function useMacroLiveEvidenceQuery({
  token,
  viewId,
  window,
}: {
  token: string;
  viewId: MacroLiveReadViewId;
  window: MacroLiveWindow;
}) {
  return useQuery({
    queryKey: ["macro", "live-evidence", viewId, window] as const,
    queryFn: async () => {
      const response = await getApi<MacroLiveEvidenceReadData>(`/api/macro/evidence/${viewId}`, {
        token,
        params: { window },
      });
      return response.data;
    },
    enabled: Boolean(token),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}
