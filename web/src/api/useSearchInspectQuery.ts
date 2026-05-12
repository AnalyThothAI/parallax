import { useQuery } from "@tanstack/react-query";

import { getApi } from "./client";
import type { ScopeKey, SearchInspectData, WindowKey } from "./types";

type SearchInspectArgs = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function useSearchInspectQuery({ q, window, scope }: SearchInspectArgs) {
  return useQuery({
    queryKey: ["search-inspect", q, window, scope],
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(q.trim()),
  });
}
