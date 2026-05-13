import type { RadarSortMode, ScopeKey, WindowKey } from "@lib/types";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { OBSERVATION_WINDOWS } from "../../../lib/observationWindows";

const VALID_SCOPES = new Set<ScopeKey>(["all", "matched"]);
const VALID_SORTS = new Set<RadarSortMode>([
  "opportunity",
  "heat",
  "quality",
  "propagation",
  "timing",
]);

export type LiveRouteState = {
  window: WindowKey;
  scope: ScopeKey;
  handles: string;
  sort: RadarSortMode;
};

export const LIVE_ROUTE_DEFAULTS: LiveRouteState = {
  window: "1h",
  scope: "all",
  handles: "",
  sort: "opportunity",
};

export function parseLiveRouteState(searchParams: URLSearchParams): LiveRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
    handles: normalizeHandles(searchParams.get("handles") ?? ""),
    sort: parseSort(searchParams.get("sort")),
  };
}

export function serializeLiveRouteState(state: LiveRouteState): URLSearchParams {
  const params = new URLSearchParams();
  const normalized = normalizeLiveRouteState(state);
  if (normalized.window !== LIVE_ROUTE_DEFAULTS.window) params.set("window", normalized.window);
  if (normalized.scope !== LIVE_ROUTE_DEFAULTS.scope) params.set("scope", normalized.scope);
  if (normalized.handles) params.set("handles", normalized.handles);
  if (normalized.sort !== LIVE_ROUTE_DEFAULTS.sort) params.set("sort", normalized.sort);
  return params;
}

export function liveRouteStateWith(
  state: LiveRouteState,
  patch: Partial<LiveRouteState>,
): LiveRouteState {
  return normalizeLiveRouteState({ ...state, ...patch });
}

export function useLiveRouteState() {
  const [searchParams, replaceUrlSearch] = useSearchParams();
  const routeState = useMemo(() => parseLiveRouteState(searchParams), [searchParams]);
  const update = (patch: Partial<LiveRouteState>) => {
    replaceUrlSearch(serializeLiveRouteState(liveRouteStateWith(routeState, patch)));
  };
  return {
    ...routeState,
    updateWindow: (window: WindowKey) => update({ window }),
    updateScope: (scope: ScopeKey) => update({ scope }),
    updateHandles: (handles: string) => update({ handles }),
    updateSort: (sort: RadarSortMode) => update({ sort }),
  };
}

function normalizeLiveRouteState(routeState: LiveRouteState): LiveRouteState {
  return {
    window: parseWindow(routeState.window),
    scope: parseScope(routeState.scope),
    handles: normalizeHandles(routeState.handles),
    sort: parseSort(routeState.sort),
  };
}

function parseWindow(value: string | null): WindowKey {
  return OBSERVATION_WINDOWS.includes(value as WindowKey)
    ? (value as WindowKey)
    : LIVE_ROUTE_DEFAULTS.window;
}

function parseScope(value: string | null): ScopeKey {
  return value && VALID_SCOPES.has(value as ScopeKey)
    ? (value as ScopeKey)
    : LIVE_ROUTE_DEFAULTS.scope;
}

function parseSort(value: string | null): RadarSortMode {
  return value && VALID_SORTS.has(value as RadarSortMode)
    ? (value as RadarSortMode)
    : LIVE_ROUTE_DEFAULTS.sort;
}

function normalizeHandles(value: string): string {
  return value
    .split(",")
    .map((item) => item.trim().replace(/^@/, "").toLowerCase())
    .filter(Boolean)
    .join(",");
}
