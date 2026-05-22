import { getApi, getAuthToken } from "@lib/api/client";
import type { ScopeKey, SearchInspectData, WindowKey } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

type SearchInspectArgs = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
  token?: string | null;
};

export function useSearchInspectQuery({ q, window, scope, token }: SearchInspectArgs) {
  const requestToken = token ?? getAuthToken();

  return useQuery({
    queryKey: queryKeys.searchInspect(requestToken ?? "", q, window, scope),
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        token: requestToken ?? undefined,
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(requestToken && q.trim()),
  });
}
