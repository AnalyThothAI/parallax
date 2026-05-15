import { getApi } from "@lib/api/client";
import type {
  TokenCaseApiScope,
  TokenCaseDossier,
  TokenCasePostsData,
  TokenPostRange,
  TokenPostServerSort,
  WindowKey,
} from "@lib/types";
import type { TokenCaseScope, TokenCaseSort } from "@shared/model/tokenCaseViewModel";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import type { TargetRef } from "../../../domain/tokenTarget";
import { targetRefKey } from "../../../domain/tokenTarget";
import { tokenCaseScopeToApiScope } from "../state/tokenCaseRouteState";

type UseTokenCaseArgs = {
  token: string;
  target: TargetRef | null;
  window: WindowKey;
  scope: TokenCaseScope;
  postsLimit?: number;
};

type UseTokenCasePostsArgs = UseTokenCaseArgs & {
  postSort: TokenCaseSort;
  range?: TokenPostRange;
  initialPosts?: TokenCasePostsData | null;
};

export function useTokenCase({
  token,
  target,
  window,
  scope,
  postsLimit = 24,
}: UseTokenCaseArgs) {
  return useQuery({
    queryKey: queryKeys.tokenCase(target ? targetRefKey(target) : null, window, scope, postsLimit),
    queryFn: () =>
      getApi<TokenCaseDossier>("/api/token-case", {
        token,
        params: {
          target_type: target?.target_type,
          target_id: target?.target_id,
          window,
          scope: tokenCaseScopeToApiScope(scope),
          posts_limit: postsLimit,
        },
      }),
    enabled: Boolean(token && target),
    staleTime: 15_000,
  });
}

export function useTokenCasePosts({
  token,
  target,
  window,
  scope,
  postsLimit = 24,
  postSort,
  range = "current_window",
  initialPosts = null,
}: UseTokenCasePostsArgs) {
  const serverSort = postSort === "catalyst" ? "catalyst" : "recent";
  const apiScope = tokenCaseScopeToApiScope(scope);
  const seedPosts = canSeedTokenCasePosts({
    initialPosts,
    target,
    window,
    scope: apiScope,
    range,
    serverSort,
  })
    ? initialPosts
    : null;
  const queryKey = queryKeys.targetPosts(
    target ? targetRefKey(target) : null,
    window,
    scope,
    range,
    serverSort,
    postsLimit,
  );

  return useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam }) => {
      const response = await getApi<TokenCasePostsData>("/api/target-posts", {
        token,
        params: {
          target_type: target?.target_type,
          target_id: target?.target_id,
          window,
          scope: apiScope,
          range,
          sort: serverSort,
          limit: postsLimit,
          cursor: serverSort === "catalyst" ? undefined : pageParam || undefined,
        },
      });
      return response.data;
    },
    initialData: seedPosts
      ? {
          pages: [seedPosts],
          pageParams: [""],
        }
      : undefined,
    initialPageParam: "",
    getNextPageParam: (lastPage) =>
      lastPage.query.sort === "catalyst" ? undefined : lastPage.next_cursor || undefined,
    enabled: Boolean(token && target && seedPosts),
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
    staleTime: 15_000,
  });
}

export function mergeTokenCasePostPages(pages?: TokenCasePostsData[]): TokenCasePostsData | null {
  if (!pages?.length) {
    return null;
  }
  const first = pages[0];
  const last = pages[pages.length - 1];
  return {
    ...first,
    returned_count: pages.reduce((total, page) => total + page.returned_count, 0),
    has_more: last.has_more,
    next_cursor: last.next_cursor,
    items: pages.flatMap((page) => page.items),
  };
}

export function canSeedTokenCasePosts({
  initialPosts,
  target,
  window,
  scope,
  range,
  serverSort,
}: {
  initialPosts?: TokenCasePostsData | null;
  target: TargetRef | null;
  window: WindowKey;
  scope: TokenCaseApiScope;
  range: TokenPostRange;
  serverSort: TokenPostServerSort;
}): boolean {
  if (!initialPosts || !target) {
    return false;
  }
  const query = initialPosts.query;
  return (
    query.target_type === target.target_type &&
    query.target_id === target.target_id &&
    query.window === window &&
    tokenCaseScopeKey(query.scope) === tokenCaseScopeKey(scope) &&
    query.range === range &&
    (query.sort ?? "recent") === serverSort
  );
}

function tokenCaseScopeKey(scope: TokenCaseApiScope): TokenCaseScope {
  return scope === "matched" ? "watched" : scope;
}
