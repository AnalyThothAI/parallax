import { getApi, getAuthToken } from "@lib/api/client";
import type { LivePayload, RecentData, SignalPulseItem } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { signalLabPulsePath } from "@shared/routing/paths";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { mergeSignalPulsePages, useSignalPulseList } from "./api/useSignalPulseQueries";
import {
  parseSignalLabRouteState,
  serializeSignalLabRouteState,
  signalLabRouteSearch,
  signalLabRouteStateWith,
  type SignalLabRouteState,
} from "./state/signalLabRouteState";

type UseSignalLabPageArgs = {
  onSelectAccountEvent?: (item: LivePayload) => void;
  token?: string;
};

export function useSignalLabPage({
  onSelectAccountEvent,
  token: tokenProp,
}: UseSignalLabPageArgs = {}) {
  const token = tokenProp ?? getAuthToken() ?? "";
  const [searchParams, replaceUrlSearch] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  const routeState = useMemo(() => parseSignalLabRouteState(searchParams), [searchParams]);
  const activeSignalLabHandle = routeState.handle;
  const effectiveStatus = routeState.visibility === "hidden" ? "all" : routeState.status;

  const signalPulseQuery = useSignalPulseList({
    token,
    window: routeState.window,
    scope: routeState.scope,
    status: effectiveStatus,
    visibility: routeState.visibility,
    handle: routeState.handle,
    q: routeState.q,
  });

  const signalLabAccountEventsQuery = useQuery({
    queryKey: queryKeys.signalLabAccountEvents(token, routeState.scope, activeSignalLabHandle),
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: {
          limit: 80,
          scope: routeState.scope,
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
  const signalLabAccountEvents = signalLabAccountEventsQuery.data?.data.items ?? [];
  const selectedPulseItemId = pulseIdFromPathname(location.pathname);

  const updateRouteState = (patch: Partial<SignalLabRouteState>, replace = true) => {
    const nextState = signalLabRouteStateWith(routeState, patch);
    replaceUrlSearch(serializeSignalLabRouteState(nextState), { replace });
  };

  const selectPulse = (item: SignalPulseItem) => {
    navigate(signalLabPulsePath(item.candidate_id, signalLabRouteSearch(routeState)));
  };

  const clearFilters = () => {
    updateRouteState({ status: "all", visibility: "public", handle: "", q: "" }, false);
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
    updateSearchFilter: (q: string) => updateRouteState({ q }),
    setStatusFilter: (status: SignalLabRouteState["status"]) => updateRouteState({ status }, false),
    setVisibilityFilter: (visibility: SignalLabRouteState["visibility"]) =>
      updateRouteState(
        {
          visibility,
          status: visibility === "hidden" ? "all" : routeState.status,
        },
        false,
      ),
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
