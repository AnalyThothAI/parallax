import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type {
  ScopeKey,
  TokenDetailTab,
  TokenPostRange,
  TokenPostSortMode,
  WindowKey,
} from "@lib/types";


const VALID_TABS = new Set<TokenDetailTab>(["timeline", "posts", "score", "lab", "accounts"]);
const VALID_RANGES = new Set<TokenPostRange>(["current_window", "since_ignition", "all_history"]);
const VALID_SORTS = new Set<TokenPostSortMode>(["recent", "quality", "catalyst"]);

export type TokenTargetRouteState = {
  window: WindowKey;
  scope: ScopeKey;
  tab: TokenDetailTab;
  postRange: TokenPostRange;
  postSort: TokenPostSortMode;
};

export const TOKEN_TARGET_ROUTE_DEFAULTS: TokenTargetRouteState = {
  window: "1h",
  scope: "all",
  tab: "timeline",
  postRange: "current_window",
  postSort: "recent",
};

export function parseTokenTargetRouteState(searchParams: URLSearchParams): TokenTargetRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
    tab: parseTab(searchParams.get("tab")),
    postRange: parseRange(searchParams.get("postRange")),
    postSort: parseSort(searchParams.get("postSort")),
  };
}

export function serializeTokenTargetRouteState(
  routeState: TokenTargetRouteState,
): URLSearchParams {
  const params = new URLSearchParams();
  const normalized: TokenTargetRouteState = {
    window: parseWindow(routeState.window),
    scope: parseScope(routeState.scope),
    tab: parseTab(routeState.tab),
    postRange: parseRange(routeState.postRange),
    postSort: parseSort(routeState.postSort),
  };
  if (normalized.window !== TOKEN_TARGET_ROUTE_DEFAULTS.window)
    params.set("window", normalized.window);
  if (normalized.scope !== TOKEN_TARGET_ROUTE_DEFAULTS.scope) params.set("scope", normalized.scope);
  if (normalized.tab !== TOKEN_TARGET_ROUTE_DEFAULTS.tab) params.set("tab", normalized.tab);
  if (normalized.postRange !== TOKEN_TARGET_ROUTE_DEFAULTS.postRange)
    params.set("postRange", normalized.postRange);
  if (normalized.postSort !== TOKEN_TARGET_ROUTE_DEFAULTS.postSort)
    params.set("postSort", normalized.postSort);
  return params;
}

function parseWindow(value: string | null): WindowKey {
  return OBSERVATION_WINDOWS.includes(value as WindowKey)
    ? (value as WindowKey)
    : TOKEN_TARGET_ROUTE_DEFAULTS.window;
}

function parseScope(value: string | null): ScopeKey {
  return value === "matched" || value === "all" ? value : TOKEN_TARGET_ROUTE_DEFAULTS.scope;
}

function parseTab(value: string | null): TokenDetailTab {
  return value && VALID_TABS.has(value as TokenDetailTab)
    ? (value as TokenDetailTab)
    : TOKEN_TARGET_ROUTE_DEFAULTS.tab;
}

function parseRange(value: string | null): TokenPostRange {
  return value && VALID_RANGES.has(value as TokenPostRange)
    ? (value as TokenPostRange)
    : TOKEN_TARGET_ROUTE_DEFAULTS.postRange;
}

function parseSort(value: string | null): TokenPostSortMode {
  return value && VALID_SORTS.has(value as TokenPostSortMode)
    ? (value as TokenPostSortMode)
    : TOKEN_TARGET_ROUTE_DEFAULTS.postSort;
}
