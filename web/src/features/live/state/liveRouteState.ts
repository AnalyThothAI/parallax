import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type { ScopeKey, WindowKey } from "@lib/types";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

const VALID_SCOPES = new Set<ScopeKey>(["all", "matched"]);

export type LiveRouteState = {
  window: WindowKey;
  scope: ScopeKey;
};

export const LIVE_ROUTE_DEFAULTS: LiveRouteState = {
  window: "1h",
  scope: "all",
};

export function parseLiveRouteState(searchParams: URLSearchParams): LiveRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
  };
}

export function serializeLiveRouteState(state: LiveRouteState): URLSearchParams {
  const params = new URLSearchParams();
  const normalized = normalizeLiveRouteState(state);
  if (normalized.window !== LIVE_ROUTE_DEFAULTS.window) params.set("window", normalized.window);
  if (normalized.scope !== LIVE_ROUTE_DEFAULTS.scope) params.set("scope", normalized.scope);
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
  };
}

function normalizeLiveRouteState(routeState: LiveRouteState): LiveRouteState {
  return {
    window: parseWindow(routeState.window),
    scope: parseScope(routeState.scope),
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
