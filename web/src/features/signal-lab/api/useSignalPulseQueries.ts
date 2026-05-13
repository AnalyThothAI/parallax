
import { getApi } from "@lib/api/client";
import type {
  ScopeKey,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStatusFilter,
  WindowKey,
} from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

type ListArgs = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  status: SignalPulseStatusFilter;
  handle: string;
  q: string;
  limit?: number;
};

export function useSignalPulseList({
  token,
  window,
  scope,
  status,
  handle,
  q,
  limit = 80,
}: ListArgs) {
  return useInfiniteQuery({
    queryKey: queryKeys.signalPulseList(window, scope, status, handle, q, limit),
    queryFn: async ({ pageParam }) => {
      const response = await getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window,
          scope,
          status: status === "all" ? undefined : status,
          handle: handle || undefined,
          q: q || undefined,
          limit,
          cursor: pageParam || undefined,
        },
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });
}

type CandidateArgs = {
  token: string;
  candidateId: string | null;
};

export function useSignalPulseCandidate({ token, candidateId }: CandidateArgs) {
  return useQuery({
    queryKey: queryKeys.signalPulseCandidate(candidateId),
    queryFn: () =>
      getApi<SignalPulseItem>("/api/signal-lab/pulse/" + encodeURIComponent(candidateId!), {
        token,
      }),
    enabled: Boolean(token && candidateId),
    staleTime: 8_000,
    retry: false,
  });
}

export function mergeSignalPulsePages(pages?: SignalPulseData[]): SignalPulseData | undefined {
  if (!pages?.length) {
    return undefined;
  }
  const first = pages[0];
  const last = pages[pages.length - 1];
  const byCandidate = new Map<string, SignalPulseItem>();
  for (const page of pages) {
    for (const item of page.items) {
      byCandidate.set(item.candidate_id, item);
    }
  }
  const items = [...byCandidate.values()];
  return {
    ...first,
    health: last.health,
    summary: last.summary,
    returned_count: items.length,
    has_more: last.has_more,
    next_cursor: last.next_cursor,
    items,
  };
}
