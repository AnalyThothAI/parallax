import { fetchNewsRows } from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

export const useNewsPageWithToken = (token: string) =>
  useQuery({
    enabled: Boolean(token),
    queryKey: queryKeys.newsRows({ limit: 100 }),
    queryFn: () => fetchNewsRows({ limit: 100, token }),
    refetchInterval: 15_000,
    staleTime: 15_000,
  });
