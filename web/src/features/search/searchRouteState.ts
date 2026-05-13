import type { ScopeKey, WindowKey } from "@lib/types";

const VALID_WINDOWS = new Set<WindowKey>(["5m", "1h", "4h", "24h"]);
const VALID_SCOPES = new Set<ScopeKey>(["all", "matched"]);

export type SearchRouteState = {
  q: string;
  window: WindowKey;
  scope: ScopeKey;
};

export function parseSearchRouteState(params: URLSearchParams): SearchRouteState {
  const windowParam = params.get("window") as WindowKey | null;
  const scopeParam = params.get("scope") as ScopeKey | null;
  return {
    q: params.get("q")?.trim() ?? "",
    window: windowParam && VALID_WINDOWS.has(windowParam) ? windowParam : "24h",
    scope: scopeParam && VALID_SCOPES.has(scopeParam) ? scopeParam : "all",
  };
}

export function serializeSearchRouteState(state: SearchRouteState): URLSearchParams {
  const next = new URLSearchParams();
  if (state.q.trim()) {
    next.set("q", state.q.trim());
  }
  next.set("window", state.window);
  next.set("scope", state.scope);
  return next;
}
