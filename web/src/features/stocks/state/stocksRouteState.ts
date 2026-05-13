import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type { ScopeKey, WindowKey } from "@lib/types";

export type StocksRouteState = {
  window: WindowKey;
  scope: ScopeKey;
};

export const STOCKS_ROUTE_DEFAULTS: StocksRouteState = {
  window: "1h",
  scope: "all",
};

export function parseStocksRouteState(searchParams: URLSearchParams): StocksRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
  };
}

export function serializeStocksRouteState(routeState: StocksRouteState): URLSearchParams {
  const params = new URLSearchParams();
  const normalized = {
    window: parseWindow(routeState.window),
    scope: parseScope(routeState.scope),
  };
  if (normalized.window !== STOCKS_ROUTE_DEFAULTS.window) params.set("window", normalized.window);
  if (normalized.scope !== STOCKS_ROUTE_DEFAULTS.scope) params.set("scope", normalized.scope);
  return params;
}

function parseWindow(value: string | null): WindowKey {
  return OBSERVATION_WINDOWS.includes(value as WindowKey)
    ? (value as WindowKey)
    : STOCKS_ROUTE_DEFAULTS.window;
}

function parseScope(value: string | null): ScopeKey {
  return value === "matched" || value === "all" ? value : STOCKS_ROUTE_DEFAULTS.scope;
}
