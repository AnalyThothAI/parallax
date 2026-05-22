import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

export const NEWS_PAGE_SIZE = 100;

export type NewsPageQueryParams = {
  cursor?: string | null;
  direction?: string | null;
  enabled?: boolean;
  limit?: number;
  status?: string | null;
};

export const useNewsPageWithToken = (
  token: string,
  {
    cursor = null,
    direction = null,
    enabled = true,
    limit = NEWS_PAGE_SIZE,
    status = null,
  }: NewsPageQueryParams = {},
) =>
  useQuery({
    enabled: Boolean(token) && enabled,
    placeholderData: (previousData) => previousData,
    queryKey: queryKeys.newsRows({ cursor, direction, limit, status }),
    queryFn: () => fetchNewsRows({ cursor, direction, limit, status, token }),
    refetchInterval: 15_000,
    staleTime: 0,
  });

export const useInfiniteNewsPageWithToken = (
  token: string,
  { direction = null, limit = NEWS_PAGE_SIZE, status = null }: Omit<NewsPageQueryParams, "cursor"> = {},
) =>
  useInfiniteQuery({
    enabled: Boolean(token),
    initialPageParam: null as string | null,
    queryKey: queryKeys.newsRowsInfinite({ direction, limit, status }),
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      fetchNewsRows({ cursor: pageParam, direction, limit, status, token }),
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 0) > 1 ? false : 15_000),
    staleTime: 15_000,
  });

export const useNewsItemWithToken = (token: string, newsItemId?: string | null) =>
  useQuery({
    enabled: Boolean(token && newsItemId),
    queryKey: queryKeys.newsItem(newsItemId ?? ""),
    queryFn: () => fetchNewsItem({ newsItemId: newsItemId ?? "", token }),
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
