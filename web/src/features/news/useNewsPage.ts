import { fetchNewsItem, fetchNewsRows } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

export const NEWS_PAGE_SIZE = 100;

export type NewsPageQueryParams = {
  content_class?: string | null;
  content_tag?: string | null;
  coverage_tag?: string | null;
  cursor?: string | null;
  decision_class?: string | null;
  direction?: string | null;
  enabled?: boolean;
  limit?: number;
  provider_type?: string | null;
  q?: string | null;
  source_role?: string | null;
  status?: string | null;
  trust_tier?: string | null;
};

export const useNewsPageWithToken = (
  token: string,
  {
    content_class = null,
    content_tag = null,
    coverage_tag = null,
    cursor = null,
    decision_class = null,
    direction = null,
    enabled = true,
    limit = NEWS_PAGE_SIZE,
    provider_type = null,
    q = null,
    source_role = null,
    status = null,
    trust_tier = null,
  }: NewsPageQueryParams = {},
) =>
  useQuery({
    enabled: Boolean(token) && enabled,
    placeholderData: (previousData) => previousData,
    queryKey: queryKeys.newsRows({
      content_class,
      content_tag,
      coverage_tag,
      cursor,
      decision_class,
      direction,
      limit,
      provider_type,
      q,
      source_role,
      status,
      trust_tier,
    }),
    queryFn: () =>
      fetchNewsRows({
        content_class,
        content_tag,
        coverage_tag,
        cursor,
        decision_class,
        direction,
        limit,
        provider_type,
        q,
        source_role,
        status,
        token,
        trust_tier,
      }),
    refetchInterval: 15_000,
    staleTime: 0,
  });

export const useInfiniteNewsPageWithToken = (
  token: string,
  {
    content_class = null,
    content_tag = null,
    coverage_tag = null,
    decision_class = null,
    direction = null,
    limit = NEWS_PAGE_SIZE,
    provider_type = null,
    q = null,
    source_role = null,
    status = null,
    trust_tier = null,
  }: Omit<NewsPageQueryParams, "cursor"> = {},
) =>
  useInfiniteQuery({
    enabled: Boolean(token),
    initialPageParam: null as string | null,
    queryKey: queryKeys.newsRowsInfinite({
      content_class,
      content_tag,
      coverage_tag,
      decision_class,
      direction,
      limit,
      provider_type,
      q,
      source_role,
      status,
      trust_tier,
    }),
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      fetchNewsRows({
        content_class,
        content_tag,
        coverage_tag,
        cursor: pageParam,
        decision_class,
        direction,
        limit,
        provider_type,
        q,
        source_role,
        status,
        token,
        trust_tier,
      }),
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
