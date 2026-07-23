import { getApi } from "@lib/api/client";
import type { components } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

export const NEWS_PAGE_SIZE = 100;

export type NewsPageQueryParams = {
  cursor?: string | null;
  enabled?: boolean;
  limit?: number;
  q?: string | null;
  status?: string | null;
};

type NewsPageData = components["schemas"]["NewsData"];
type NewsItemData = components["schemas"]["NewsObjectData"];

export const useNewsPageWithToken = (
  token: string,
  {
    cursor = null,
    enabled = true,
    limit = NEWS_PAGE_SIZE,
    q = null,
    status = null,
  }: NewsPageQueryParams = {},
) =>
  useQuery({
    enabled: Boolean(token) && enabled,
    queryKey: ["news", limit, cursor ?? "", status ?? "", q ?? ""] as const,
    queryFn: async () =>
      (
        await getApi<NewsPageData>("/api/news", {
          params: { cursor, limit, q, status },
          token,
        })
      ).data,
    refetchInterval: 15_000,
    staleTime: 0,
  });

export const useInfiniteNewsPageWithToken = (
  token: string,
  { limit = NEWS_PAGE_SIZE, q = null, status = null }: Omit<NewsPageQueryParams, "cursor"> = {},
) =>
  useInfiniteQuery({
    enabled: Boolean(token),
    initialPageParam: null as string | null,
    queryKey: ["news", "infinite", limit, status ?? "", q ?? ""] as const,
    queryFn: async ({ pageParam }: { pageParam: string | null }) =>
      (
        await getApi<NewsPageData>("/api/news", {
          params: { cursor: pageParam, limit, q, status },
          token,
        })
      ).data,
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    refetchInterval: (query) => ((query.state.data?.pages.length ?? 0) > 1 ? false : 15_000),
    staleTime: 15_000,
  });

export const useNewsItemWithToken = (token: string, newsItemId?: string | null) =>
  useQuery({
    enabled: Boolean(token && newsItemId),
    queryKey: queryKeys.newsItem(newsItemId ?? ""),
    queryFn: async () =>
      (
        await getApi<NewsItemData>(`/api/news/items/${encodeURIComponent(newsItemId ?? "")}`, {
          token,
        })
      ).data,
    refetchInterval: 30_000,
    staleTime: 30_000,
  });
