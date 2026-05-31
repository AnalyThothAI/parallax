import { getApi } from "@lib/api/client";
import type {
  ScopeKey,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStatusFilter,
  SignalPulseVisibilityFilter,
  SourceEventDetail,
  SourceEventsByIdsData,
  WindowKey,
} from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

type ListArgs = {
  token: string;
  window: WindowKey;
  scope: ScopeKey;
  status: SignalPulseStatusFilter;
  visibility: SignalPulseVisibilityFilter;
  handle: string;
  q: string;
  limit?: number;
};

export function useSignalPulseList({
  token,
  window,
  scope,
  status,
  visibility,
  handle,
  q,
  limit = 80,
}: ListArgs) {
  return useInfiniteQuery({
    queryKey: queryKeys.signalPulseList(window, scope, status, visibility, handle, q, limit),
    queryFn: async ({ pageParam }) => {
      const response = await getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window,
          scope,
          status: visibility === "public" && status !== "all" ? status : undefined,
          visibility: visibility === "hidden" ? visibility : undefined,
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
  visibility?: SignalPulseVisibilityFilter;
};

export function useSignalPulseCandidate({
  token,
  candidateId,
  visibility = "public",
}: CandidateArgs) {
  return useQuery({
    queryKey: queryKeys.signalPulseCandidate(candidateId, visibility),
    queryFn: () =>
      getApi<SignalPulseItem>("/api/signal-lab/pulse/" + encodeURIComponent(candidateId!), {
        token,
        params: { visibility: visibility === "hidden" ? visibility : undefined },
      }),
    enabled: Boolean(token && candidateId),
    staleTime: 8_000,
    retry: false,
  });
}

type SourceEventsArgs = {
  token: string;
  ids: string[];
};

export function useSourceEvents({ token, ids }: SourceEventsArgs) {
  const normalizedIds = ids.filter(Boolean);
  return useQuery({
    queryKey: queryKeys.sourceEventsByIds(normalizedIds),
    queryFn: async (): Promise<SourceEventDetail[]> => {
      const response = await getApi<SourceEventsByIdsData>("/api/events/by-ids", {
        token,
        params: { ids: normalizedIds.join(",") },
      });
      return response.data.events;
    },
    enabled: Boolean(token) && normalizedIds.length > 0,
    staleTime: 30_000,
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
