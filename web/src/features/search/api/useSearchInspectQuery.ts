import { getApi, getAuthToken } from "@lib/api/client";
import type { ScopeKey, SearchInspectData, WindowKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

type SearchInspectArgs = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function useSearchInspectQuery({ q, window, scope }: SearchInspectArgs) {
  const token = getAuthToken();

  return useQuery({
    queryKey: queryKeys.searchInspect(token ?? "", q, window, scope),
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        token: token ?? undefined,
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(token && q.trim()),
  });
}
