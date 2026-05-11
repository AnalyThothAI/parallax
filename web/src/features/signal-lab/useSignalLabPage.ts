import { useMemo } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getApi } from "../../api/client";
import { mergeSignalPulsePages, useSignalPulseList } from "../../api/useSignalPulseQueries";
import type { LivePayload, RecentData, SignalPulseItem } from "../../api/types";
import { useTraderStore } from "../../store/useTraderStore";
import {
  parseSignalLabRouteState,
  serializeSignalLabRouteState,
  signalLabRouteSearch,
  signalLabRouteStateWith,
  type SignalLabRouteState
} from "./signalLabRouteState";

type UseSignalLabPageArgs = {
  onSelectAccountEvent?: (item: LivePayload) => void;
};

export function useSignalLabPage({ onSelectAccountEvent }: UseSignalLabPageArgs = {}) {
  const token = useTraderStore((state) => state.token);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  const routeState = useMemo(() => parseSignalLabRouteState(searchParams), [searchParams]);
  const activeSignalLabHandle = routeState.handle;

  const signalPulseQuery = useSignalPulseList({
    token,
    window: routeState.window,
    scope: routeState.scope,
    status: routeState.status,
    handle: routeState.handle,
    q: routeState.q
  });

  const signalLabAccountEventsQuery = useQuery({
    queryKey: ["signal-lab-account-events", token, routeState.scope, activeSignalLabHandle],
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: {
          limit: 80,
          scope: routeState.scope,
          handles: activeSignalLabHandle
        }
      }),
    enabled: Boolean(token && activeSignalLabHandle),
    refetchInterval: 15_000
  });

  const signalPulseData = useMemo(
    () => mergeSignalPulsePages(signalPulseQuery.data?.pages),
    [signalPulseQuery.data?.pages]
  );
  const signalLabAccountEvents = signalLabAccountEventsQuery.data?.data.items ?? [];
  const selectedPulseItemId = pulseIdFromPathname(location.pathname);

  const updateRouteState = (patch: Partial<SignalLabRouteState>, replace = true) => {
    const nextState = signalLabRouteStateWith(routeState, patch);
    setSearchParams(serializeSignalLabRouteState(nextState), { replace });
  };

  const selectPulse = (item: SignalPulseItem) => {
    navigate(`/signal-lab/pulse/${encodeURIComponent(item.candidate_id)}${signalLabRouteSearch(routeState)}`);
  };

  const clearFilters = () => {
    updateRouteState({ status: "all", handle: "", q: "" }, false);
  };

  const selectAccountEvent = (item: LivePayload) => {
    onSelectAccountEvent?.(item);
  };

  return {
    routeState,
    selectedPulseItemId,
    isPulseRoute: Boolean(selectedPulseItemId),
    signalPulseData,
    signalLabAccountEvents,
    isSignalPulseLoading: signalPulseQuery.isPending,
    isFetchingNextPage: signalPulseQuery.isFetchingNextPage,
    hasNextPage: Boolean(signalPulseQuery.hasNextPage),
    isAccountEventsLoading: signalLabAccountEventsQuery.isPending && !signalLabAccountEvents.length,
    clearFilters,
    loadMore: () => void signalPulseQuery.fetchNextPage(),
    selectAccountEvent,
    selectPulse,
    setHandleFilter: (handle: string) => updateRouteState({ handle }),
    setSearchFilter: (q: string) => updateRouteState({ q }),
    setStatusFilter: (status: SignalLabRouteState["status"]) => updateRouteState({ status }, false)
  };
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
