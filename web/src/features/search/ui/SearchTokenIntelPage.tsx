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
  const vm = useMemo(
    () =>
      buildTokenCaseViewModel({
        dossier: result,
        route: {
          window: routeState.window,
          scope: tokenCaseScopeFromSearchScope(routeState.scope),
          postSort,
        },
        posts: result.posts,
        isLoadingPosts: false,
        isFetchingNextPage: false,
      }),
    [postSort, result, routeState.scope, routeState.window],
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
