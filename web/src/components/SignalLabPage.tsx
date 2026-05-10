import { useEffect, useMemo } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getApi } from "../api/client";
import type {
  LivePayload,
  RecentData,
  SignalPulseData,
  SignalPulseItem
} from "../api/types";
import { useTraderStore } from "../store/useTraderStore";
import { SignalLabWorkbench } from "./SignalLabWorkbench";

const SIGNAL_LAB_SCOPE = "all";
const SIGNAL_LAB_WINDOW = "1h";

type SignalLabPageProps = {
  selectedPulseItemId: string | null;
  selectedAccountEventId: string | null;
  overviewData?: SignalPulseData;
  onSelectPulse: (item: SignalPulseItem, options?: { openLab?: boolean }) => void;
  onSelectAccountEvent: (item: LivePayload) => void;
  onClearSelection: () => void;
};

export function SignalLabPage({
  selectedPulseItemId,
  selectedAccountEventId,
  overviewData,
  onSelectPulse,
  onSelectAccountEvent,
  onClearSelection
}: SignalLabPageProps) {
  const token = useTraderStore((state) => state.token);
  const signalLabStatus = useTraderStore((state) => state.signalLabStatus);
  const signalLabHandle = useTraderStore((state) => state.signalLabHandle);
  const signalLabSearch = useTraderStore((state) => state.signalLabSearch);
  const setSignalLabStatus = useTraderStore((state) => state.setSignalLabStatus);
  const setSignalLabHandle = useTraderStore((state) => state.setSignalLabHandle);
  const setSignalLabSearch = useTraderStore((state) => state.setSignalLabSearch);

  const activeSignalLabHandle = normalizedHandle(signalLabHandle);

  const signalPulseQuery = useInfiniteQuery({
    queryKey: ["signal-lab-pulse", SIGNAL_LAB_WINDOW, SIGNAL_LAB_SCOPE, signalLabStatus, signalLabHandle, signalLabSearch],
    queryFn: async ({ pageParam }) => {
      const response = await getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: SIGNAL_LAB_WINDOW,
          scope: SIGNAL_LAB_SCOPE,
          status: signalLabStatus === "all" ? undefined : signalLabStatus,
          handle: signalLabHandle || undefined,
          q: signalLabSearch || undefined,
          limit: 80,
          cursor: pageParam || undefined
        }
      });
      return response.data;
    },
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const signalLabAccountEventsQuery = useQuery({
    queryKey: ["signal-lab-account-events", SIGNAL_LAB_SCOPE, activeSignalLabHandle],
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: {
          limit: 80,
          scope: SIGNAL_LAB_SCOPE,
          handles: activeSignalLabHandle
        }
      }),
    enabled: Boolean(token && activeSignalLabHandle),
    refetchInterval: 15_000
  });

  const signalPulseData = useMemo(() => mergeSignalPulsePages(signalPulseQuery.data?.pages), [signalPulseQuery.data?.pages]);
  const workbenchSignalPulseItems = signalPulseData?.items ?? [];
  const signalLabAccountEvents = signalLabAccountEventsQuery.data?.data.items ?? [];

  // Auto-select preferred pulse item when entering Signal Lab and no selection yet.
  useEffect(() => {
    if (selectedPulseItemId || !workbenchSignalPulseItems.length) {
      return;
    }
    const preferred = preferredPulseItem(workbenchSignalPulseItems);
    onSelectPulse(preferred);
  }, [onSelectPulse, selectedPulseItemId, workbenchSignalPulseItems]);

  const handleClearFilters = () => {
    setSignalLabStatus("all");
    setSignalLabHandle("");
    setSignalLabSearch("");
    onClearSelection();
  };

  return (
    <section className="mobile-task-surface signal-lab-task-surface" data-mobile-task-panel="lab">
      <SignalLabWorkbench
        data={signalPulseData}
        accountEvents={signalLabAccountEvents}
        handleFilter={signalLabHandle}
        isAccountEventsLoading={signalLabAccountEventsQuery.isPending && !signalLabAccountEvents.length}
        isLoading={signalPulseQuery.isPending}
        isFetchingNextPage={signalPulseQuery.isFetchingNextPage}
        hasNextPage={Boolean(signalPulseQuery.hasNextPage)}
        overviewData={overviewData}
        searchFilter={signalLabSearch}
        selectedAccountEventId={selectedAccountEventId}
        selectedItemId={selectedPulseItemId}
        statusFilter={signalLabStatus}
        windowLabel={SIGNAL_LAB_WINDOW}
        onClearFilters={handleClearFilters}
        onHandleChange={setSignalLabHandle}
        onLoadMore={() => void signalPulseQuery.fetchNextPage()}
        onSearchChange={setSignalLabSearch}
        onSelectAccountEvent={onSelectAccountEvent}
        onSelect={onSelectPulse}
        onStatusChange={setSignalLabStatus}
      />
    </section>
  );
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function mergeSignalPulsePages(pages?: SignalPulseData[]): SignalPulseData | undefined {
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
    items
  };
}

function preferredPulseItem(items: SignalPulseItem[]): SignalPulseItem {
  return [...items].sort(
    (a, b) =>
      pulseStatusRank(b) - pulseStatusRank(a) ||
      Number(b.candidate_score ?? 0) - Number(a.candidate_score ?? 0) ||
      b.updated_at_ms - a.updated_at_ms
  )[0];
}

function pulseStatusRank(item: SignalPulseItem): number {
  if (item.pulse_status === "trade_candidate") return 4;
  if (item.pulse_status === "token_watch") return 3;
  if (item.pulse_status === "theme_watch") return 2;
  return 1;
}
