import { useSearchParams } from "react-router-dom";

import { normalizeWatchlistHandle } from "../model/watchlistCase";

export type WatchlistRouteState = {
  selectedHandle: string | null;
};

export function parseWatchlistRouteState(
  searchParams: URLSearchParams,
  defaultHandle: string | null,
): WatchlistRouteState {
  const selectedHandle = normalizeWatchlistHandle(searchParams.get("handle")) ?? defaultHandle;
  return { selectedHandle };
}

export function useWatchlistRouteState(defaultHandle: string | null) {
  const [searchParams] = useSearchParams();
  return parseWatchlistRouteState(searchParams, defaultHandle);
}
