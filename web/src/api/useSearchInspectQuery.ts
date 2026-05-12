import { useQuery } from "@tanstack/react-query";

import { getApi } from "./client";
import type { ScopeKey, SearchInspectData, WindowKey } from "./types";
import { useTraderStore } from "../store/useTraderStore";

type SearchInspectArgs = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function useSearchInspectQuery({ q, window, scope }: SearchInspectArgs) {
  const token = useTraderStore((state) => state.token);

  return useQuery({
    queryKey: ["search-inspect", token, q, window, scope],
    queryFn: () =>
      getApi<SearchInspectData>("/api/search/inspect", {
        token,
        params: { q, window, scope, limit: 200 },
      }),
    enabled: Boolean(token && q.trim()),
  });
}
