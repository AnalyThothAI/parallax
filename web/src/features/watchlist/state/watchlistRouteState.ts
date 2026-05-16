import type { WatchlistTimelineScope } from "@lib/types";
import { useSearchParams } from "react-router-dom";

import { normalizeWatchlistHandle } from "../model/watchlistCase";

const SCOPES = new Set<WatchlistTimelineScope>(["signal", "all"]);

export type WatchlistRouteState = {
  selectedHandle: string | null;
  timelineScope: WatchlistTimelineScope;
};

export function parseWatchlistRouteState(
  searchParams: URLSearchParams,
  defaultHandle: string | null,
): WatchlistRouteState {
  const selectedHandle = normalizeWatchlistHandle(searchParams.get("handle")) ?? defaultHandle;
  const rawTimelineScope = searchParams.get("timeline_scope") as WatchlistTimelineScope | null;
  return {
    selectedHandle,
    timelineScope: rawTimelineScope && SCOPES.has(rawTimelineScope) ? rawTimelineScope : "signal",
  };
}

export function serializeWatchlistTimelineScope(
  current: URLSearchParams,
  nextScope: WatchlistTimelineScope,
  selectedHandle: string | null,
): URLSearchParams {
  const next = new URLSearchParams(current);
  next.delete("scope");
  next.set("timeline_scope", nextScope);
  if (selectedHandle) {
    next.set("handle", selectedHandle);
  }
  return next;
}

export function useWatchlistRouteState(defaultHandle: string | null) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedHandle, timelineScope } = parseWatchlistRouteState(searchParams, defaultHandle);

  const updateTimelineScope = (nextScope: WatchlistTimelineScope) => {
    setSearchParams((current) => {
      return serializeWatchlistTimelineScope(current, nextScope, selectedHandle);
    });
  };

  return { selectedHandle, timelineScope, updateTimelineScope };
}
