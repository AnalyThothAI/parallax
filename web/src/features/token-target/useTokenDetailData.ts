import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { getApi } from "../../api/client";
import type {
  AccountQualityData,
  ScopeKey,
  TokenPostRange,
  TokenPostSortMode,
  WindowKey,
} from "../../api/types";
import {
  mergeTokenPostPages,
  useTokenTargetPosts,
  useTokenTargetTimeline,
} from "../../api/useTokenTargetQueries";
import type { TargetRef } from "../../domain/tokenTarget";

type UseTokenDetailDataArgs = {
  detailWindow: WindowKey;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  scope: ScopeKey;
  target: TargetRef | null;
  token: string;
};

export function useTokenDetailData({
  detailWindow,
  postRange,
  postSortMode,
  scope,
  target,
  token,
}: UseTokenDetailDataArgs) {
  const tokenTimelineQuery = useTokenTargetTimeline({ token, target, window: detailWindow, scope });
  const tokenPostsQuery = useTokenTargetPosts({
    token,
    target,
    window: detailWindow,
    scope,
    range: postRange,
    sort: postSortMode === "catalyst" ? "catalyst" : "recent",
  });

  const accountQualityHandles = useMemo(
    () =>
      (tokenTimelineQuery.data?.data.authors ?? [])
        .map((author) => author.handle)
        .filter(Boolean)
        .join(","),
    [tokenTimelineQuery.data?.data.authors],
  );
  const accountQualityQuery = useQuery({
    queryKey: ["account-quality", accountQualityHandles],
    queryFn: () =>
      getApi<AccountQualityData>("/api/account-quality", {
        token,
        params: { handles: accountQualityHandles },
      }),
    enabled: Boolean(token && accountQualityHandles),
  });

  return {
    accountQuality: accountQualityQuery.data?.data,
    isAccountQualityLoading: accountQualityQuery.isFetching,
    isPostsFetchingNextPage: tokenPostsQuery.isFetchingNextPage,
    isPostsLoading: tokenPostsQuery.isLoading,
    isTimelineLoading: tokenTimelineQuery.isFetching,
    loadMorePosts: () => void tokenPostsQuery.fetchNextPage(),
    posts: mergeTokenPostPages(tokenPostsQuery.data?.pages),
    timeline: tokenTimelineQuery.data?.data,
  };
}
