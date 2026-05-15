import { getApi } from "@lib/api/client";
import type { TokenCaseDossier, TokenPostRange, TokenPostsData, WindowKey } from "@lib/types";
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
  initialPosts?: TokenPostsData | null;
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
      const response = await getApi<TokenPostsData>("/api/target-posts", {
        token,
        params: {
          target_type: target?.target_type,
          target_id: target?.target_id,
          window,
          scope: tokenCaseScopeToApiScope(scope),
          range,
          sort: serverSort,
          limit: postsLimit,
          cursor: serverSort === "catalyst" ? undefined : pageParam || undefined,
        },
      });
      return response.data;
    },
    initialData: initialPosts
      ? {
          pages: [initialPosts],
          pageParams: [""],
        }
      : undefined,
    initialPageParam: "",
    getNextPageParam: (lastPage) =>
      lastPage.query.sort === "catalyst" ? undefined : lastPage.next_cursor || undefined,
    enabled: Boolean(token && target),
    staleTime: 15_000,
  });
}

export function mergeTokenCasePostPages(pages?: TokenPostsData[]): TokenPostsData | null {
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
