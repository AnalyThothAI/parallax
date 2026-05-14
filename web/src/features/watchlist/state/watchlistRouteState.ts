import type { WatchlistTimelineScope } from "@lib/types";
import { useSearchParams } from "react-router-dom";

import { normalizeWatchlistHandle } from "../model/watchlistCase";

const SCOPES = new Set<WatchlistTimelineScope>(["signal", "all"]);

export function useWatchlistRouteState(defaultHandle: string | null) {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedHandle = normalizeWatchlistHandle(searchParams.get("handle")) ?? defaultHandle;
  const rawScope = searchParams.get("scope") as WatchlistTimelineScope | null;
  const scope: WatchlistTimelineScope = rawScope && SCOPES.has(rawScope) ? rawScope : "signal";

  const updateScope = (nextScope: WatchlistTimelineScope) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set("scope", nextScope);
      if (selectedHandle) {
        next.set("handle", selectedHandle);
      }
      return next;
    });
  };

  return { scope, selectedHandle, updateScope };
}
