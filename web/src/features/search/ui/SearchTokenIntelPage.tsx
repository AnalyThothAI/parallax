import { buildTokenCaseViewModel } from "@features/token-case";
import type { ScopeKey, SearchInspectData, SearchTokenResult } from "@lib/types";
import type { TokenCaseScope, TokenCaseSort } from "@shared/model/tokenCaseViewModel";
import { TokenCasePanel } from "@shared/ui/case-file";
import { useMemo, useState } from "react";

import type { SearchRouteState } from "../state/searchRouteState";

type SearchTokenIntelPageProps = {
  data: SearchInspectData;
  result: SearchTokenResult;
  routeState: SearchRouteState;
  onRouteChange: (patch: Partial<SearchRouteState>) => void;
};

export function SearchTokenIntelPage({
  data: _data,
  result,
  routeState,
  onRouteChange,
}: SearchTokenIntelPageProps) {
  const [postSort, setPostSort] = useState<TokenCaseSort>("recent");
  const searchPosts = useMemo(
    () => ({
      ...result.posts,
      has_more: false,
      next_cursor: null,
    }),
    [result.posts],
  );
  const vm = useMemo(
    () =>
      buildTokenCaseViewModel({
        dossier: result,
        route: {
          window: routeState.window,
          scope: tokenCaseScopeFromSearchScope(routeState.scope),
          postSort,
        },
        posts: searchPosts,
        isLoadingPosts: false,
        isFetchingNextPage: false,
      }),
    [postSort, result, routeState.scope, routeState.window, searchPosts],
  );

  return (
    <TokenCasePanel
      vm={vm}
      onWindowChange={(window) => onRouteChange({ window })}
      onScopeChange={(scope) => onRouteChange({ scope: searchScopeFromTokenCaseScope(scope) })}
      onTimelineSortChange={setPostSort}
      onLoadMorePosts={() => undefined}
    />
  );
}

function tokenCaseScopeFromSearchScope(scope: ScopeKey): TokenCaseScope {
  return scope === "matched" ? "watched" : "all";
}

function searchScopeFromTokenCaseScope(scope: TokenCaseScope): ScopeKey {
  return scope === "watched" ? "matched" : "all";
}
