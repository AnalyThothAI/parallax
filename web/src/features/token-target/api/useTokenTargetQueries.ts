import { getApi } from "@lib/api/client";
import type {
  AssetFlowData,
  ScopeKey,
  TokenPostRange,
  TokenPostServerSort,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey,
} from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import type { TargetRef } from "../../../domain/tokenTarget";
import { targetRefKey } from "../../../domain/tokenTarget";

type TimelineArgs = {
  token: string;
  target: TargetRef | null;
  window: WindowKey;
  scope: ScopeKey;
};

type PostsArgs = TimelineArgs & {
  range: TokenPostRange;
  sort: TokenPostServerSort;
  limit?: number;
};

export function useTokenTargetRadarQuery({
  token,
  window,
  scope,
  limit = 48,
  enabled = true,
}: {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  limit?: number;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.tokenRadar(window, scope, limit),
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window, limit, scope },
      }),
    enabled: Boolean(token) && enabled,
    refetchInterval: 10_000,
  });
}

export function useTokenTargetTimeline({ token, target, window, scope }: TimelineArgs) {
  return useQuery({
    queryKey: queryKeys.targetSocialTimeline(target ? targetRefKey(target) : null, window, scope),
    queryFn: () =>
      getApi<TokenSocialTimelineData>("/api/target-social-timeline", {
        token,
        params: target ? { ...target, window, scope } : {},
      }),
    enabled: Boolean(token && target),
  });
}

export function useTokenTargetPosts({
  token,
  target,
  window,
  scope,
  range,
  sort,
  limit = 24,
}: PostsArgs) {
  return useInfiniteQuery({
    queryKey: queryKeys.targetPosts(
      target ? targetRefKey(target) : null,
      window,
      scope,
      range,
      sort,
      limit,
    ),
    queryFn: async ({ pageParam }) => {
      const response = await getApi<TokenPostsData>("/api/target-posts", {
        token,
        params: {
          target_type: target?.target_type,
          target_id: target?.target_id,
          window,
          scope,
          range,
          sort,
          limit,
          cursor: sort === "catalyst" ? undefined : pageParam || undefined,
        },
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) =>
      lastPage.query.sort === "catalyst" ? undefined : lastPage.next_cursor || undefined,
    enabled: Boolean(token && target),
  });
}

export function mergeTokenPostPages(pages?: TokenPostsData[]): TokenPostsData | null {
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
