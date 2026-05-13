import { getApi } from "@lib/api/client";
import type {
  AccountQualityData,
  ScopeKey,
  TokenPostRange,
  TokenPostSortMode,
  WindowKey,
} from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { TargetRef } from "../../domain/tokenTarget";

import {
  mergeTokenPostPages,
  useTokenTargetPosts,
  useTokenTargetTimeline,
} from "./api/useTokenTargetQueries";

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
    queryKey: queryKeys.accountQuality(accountQualityHandles),
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
