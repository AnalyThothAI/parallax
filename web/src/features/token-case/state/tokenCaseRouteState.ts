import type { WindowKey } from "@lib/types";
import type { TokenCaseScope, TokenCaseSort } from "@shared/model/tokenCaseViewModel";

const VALID_WINDOWS = new Set<WindowKey>(["5m", "1h", "4h", "24h"]);
const VALID_SORTS = new Set<TokenCaseSort>(["catalyst", "recent", "watched"]);

export type TokenCaseRouteState = {
  window: WindowKey;
  scope: TokenCaseScope;
  postSort: TokenCaseSort;
};

export const TOKEN_CASE_ROUTE_DEFAULTS: TokenCaseRouteState = {
  window: "24h",
  scope: "all",
  postSort: "recent",
};

export function parseTokenCaseRouteState(searchParams: URLSearchParams): TokenCaseRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
    postSort: parseSort(searchParams.get("postSort")),
  };
}

export function serializeTokenCaseRouteState(routeState: TokenCaseRouteState): URLSearchParams {
  const params = new URLSearchParams();
  const normalized: TokenCaseRouteState = {
    window: parseWindow(routeState.window),
    scope: parseScope(routeState.scope),
    postSort: parseSort(routeState.postSort),
  };
  if (normalized.window !== TOKEN_CASE_ROUTE_DEFAULTS.window) {
    params.set("window", normalized.window);
  }
  if (normalized.scope !== TOKEN_CASE_ROUTE_DEFAULTS.scope) {
    params.set("scope", normalized.scope);
  }
  if (normalized.postSort !== TOKEN_CASE_ROUTE_DEFAULTS.postSort) {
    params.set("postSort", normalized.postSort);
  }
  return params;
}

export function tokenCaseScopeToApiScope(scope: TokenCaseScope): "all" | "watched" {
  return scope;
}

function parseWindow(value: string | null): WindowKey {
  return value && VALID_WINDOWS.has(value as WindowKey)
    ? (value as WindowKey)
    : TOKEN_CASE_ROUTE_DEFAULTS.window;
}

function parseScope(value: string | null): TokenCaseScope {
  if (value === "watched" || value === "matched") {
    return "watched";
  }
  return value === "all" ? "all" : TOKEN_CASE_ROUTE_DEFAULTS.scope;
}

function parseSort(value: string | null): TokenCaseSort {
  return value && VALID_SORTS.has(value as TokenCaseSort)
    ? (value as TokenCaseSort)
    : TOKEN_CASE_ROUTE_DEFAULTS.postSort;
}
