import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import type { TargetRef } from "../domain/tokenTarget";
import { targetRefKey } from "../domain/tokenTarget";

import { getApi } from "./client";
import type {
  ScopeKey,
  TokenPostRange,
  TokenPostServerSort,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey,
} from "./types";

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

export function useTokenTargetTimeline({ token, target, window, scope }: TimelineArgs) {
  return useQuery({
    queryKey: ["target-social-timeline", target ? targetRefKey(target) : null, window, scope],
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
    queryKey: [
      "target-posts",
      target ? targetRefKey(target) : null,
      window,
      scope,
      range,
      sort,
      limit,
    ],
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
