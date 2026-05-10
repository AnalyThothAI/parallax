import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { getApi } from "../api/client";
import type {
  LivePayload,
  RecentData,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStatusFilter,
} from "../api/types";
import { mergeSignalPulsePages, useSignalPulseList } from "../api/useSignalPulseQueries";
import { useTraderStore } from "../store/useTraderStore";

import { SignalLabWorkbench } from "./SignalLabWorkbench";

const SIGNAL_LAB_SCOPE = "all";
const SIGNAL_LAB_WINDOW = "1h";

type SignalLabPageProps = {
  selectedAccountEventId?: string | null;
  overviewData?: SignalPulseData;
  onSelectAccountEvent?: (item: LivePayload) => void;
};

export function SignalLabPage({
  selectedAccountEventId = null,
  overviewData,
  onSelectAccountEvent,
}: SignalLabPageProps) {
  const token = useTraderStore((state) => state.token);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  const handleParam = searchParams.get("handle") ?? "";
  const statusParam = (searchParams.get("status") ?? "all") as SignalPulseStatusFilter;
  const queryParam = searchParams.get("q") ?? "";

  const activeSignalLabHandle = normalizedHandle(handleParam);

  const signalPulseQuery = useSignalPulseList({
    token,
    window: SIGNAL_LAB_WINDOW,
    scope: SIGNAL_LAB_SCOPE,
    status: statusParam,
    handle: handleParam,
    q: queryParam,
  });

  const signalLabAccountEventsQuery = useQuery({
    queryKey: ["signal-lab-account-events", SIGNAL_LAB_SCOPE, activeSignalLabHandle],
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: {
          limit: 80,
          scope: SIGNAL_LAB_SCOPE,
          handles: activeSignalLabHandle,
        },
      }),
    enabled: Boolean(token && activeSignalLabHandle),
    refetchInterval: 15_000,
  });

  const signalPulseData = useMemo(
    () => mergeSignalPulsePages(signalPulseQuery.data?.pages),
    [signalPulseQuery.data?.pages],
  );
  const workbenchSignalPulseItems = useMemo(
    () => signalPulseData?.items ?? [],
    [signalPulseData?.items],
  );
  const signalLabAccountEvents = signalLabAccountEventsQuery.data?.data.items ?? [];

  // Pulse selection now lives in the URL path: /signal-lab/pulse/<candidateId>.
  const selectedPulseItemId = pulseIdFromPathname(location.pathname);
  const isPulseRoute = Boolean(selectedPulseItemId);

  // When entering /signal-lab with no pulse selected yet, auto-redirect to a preferred
  // candidate so the inspector pane shows something meaningful.
  useEffect(() => {
    if (isPulseRoute || !workbenchSignalPulseItems.length) {
      return;
    }
    const preferred = preferredPulseItem(workbenchSignalPulseItems);
    navigate(`/signal-lab/pulse/${encodeURIComponent(preferred.candidate_id)}${location.search}`, {
      replace: true,
    });
  }, [isPulseRoute, location.search, navigate, workbenchSignalPulseItems]);

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    const isDefault = key === "status" ? value === "all" : value === "";
    if (value && !isDefault) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next, { replace: false });
  };

  const handleSelectPulse = (item: SignalPulseItem) => {
    navigate(`/signal-lab/pulse/${encodeURIComponent(item.candidate_id)}${location.search}`);
  };

  const handleClearFilters = () => {
    setSearchParams(new URLSearchParams(), { replace: false });
  };

  const handleSelectAccountEvent = (item: LivePayload) => {
    if (onSelectAccountEvent) {
      onSelectAccountEvent(item);
    }
  };

  return (
    <section
      className={`mobile-task-surface signal-lab-task-surface signal-lab-layout${isPulseRoute ? " signal-lab-layout-with-detail" : ""}`}
      data-mobile-task-panel="lab"
    >
      <div className="signal-lab-list">
        <SignalLabWorkbench
          data={signalPulseData}
          accountEvents={signalLabAccountEvents}
          handleFilter={handleParam}
          isAccountEventsLoading={
            signalLabAccountEventsQuery.isPending && !signalLabAccountEvents.length
          }
          isLoading={signalPulseQuery.isPending}
          isFetchingNextPage={signalPulseQuery.isFetchingNextPage}
          hasNextPage={Boolean(signalPulseQuery.hasNextPage)}
          overviewData={overviewData}
          searchFilter={queryParam}
          selectedAccountEventId={selectedAccountEventId}
          selectedItemId={selectedPulseItemId}
          statusFilter={statusParam}
          windowLabel={SIGNAL_LAB_WINDOW}
          onClearFilters={handleClearFilters}
          onHandleChange={(value) => updateParam("handle", value)}
          onLoadMore={() => void signalPulseQuery.fetchNextPage()}
          onSearchChange={(value) => updateParam("q", value)}
          onSelectAccountEvent={handleSelectAccountEvent}
          onSelect={handleSelectPulse}
          onStatusChange={(value) => updateParam("status", value)}
        />
      </div>
      <aside className="signal-lab-inspector-pane">
        <Outlet />
      </aside>
    </section>
  );
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function pulseIdFromPathname(pathname: string): string | null {
  const prefix = "/signal-lab/pulse/";
  if (!pathname.startsWith(prefix)) {
    return null;
  }
  const tail = pathname.slice(prefix.length);
  if (!tail) {
    return null;
  }
  try {
    return decodeURIComponent(tail.split("/")[0]);
  } catch {
    return tail.split("/")[0];
  }
}

function preferredPulseItem(items: SignalPulseItem[]): SignalPulseItem {
  return [...items].sort(
    (a, b) =>
      pulseStatusRank(b) - pulseStatusRank(a) ||
      Number(b.candidate_score ?? 0) - Number(a.candidate_score ?? 0) ||
      b.updated_at_ms - a.updated_at_ms,
  )[0];
}

function pulseStatusRank(item: SignalPulseItem): number {
  if (item.pulse_status === "trade_candidate") return 4;
  if (item.pulse_status === "token_watch") return 3;
  if (item.pulse_status === "theme_watch") return 2;
  return 1;
}
