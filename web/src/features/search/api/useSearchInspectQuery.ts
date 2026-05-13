
import { getApi } from "@lib/api/client";
import type { ScopeKey, SearchInspectData, WindowKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import { useTraderStore } from "../../../store/useTraderStore";

type SearchInspectArgs = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function useSearchInspectQuery({ q, window, scope }: SearchInspectArgs) {
  const token = useTraderStore((state) => state.token);

  return useQuery({
    queryKey: queryKeys.searchInspect(token, q, window, scope),
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        token,
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(token && q.trim()),
  });
}
