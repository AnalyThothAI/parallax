import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";

import { serializeSearchRouteState } from "./searchRouteState";

export function tokenSearchQuery(item: TokenFlowItem): string {
  const symbol = item.identity.symbol?.trim();
  if (symbol) {
    return symbol.startsWith("$") ? symbol : `$${symbol}`;
  }

  const address = item.identity.address?.trim();
  if (address) {
    return address;
  }

  const instId = item.identity.inst_id?.trim();
  if (instId) {
    return instId;
  }

  return item.identity.identity_key;
}

export function tokenSearchPath(item: TokenFlowItem, window: WindowKey, scope: ScopeKey): string {
  const params = serializeSearchRouteState({
    q: tokenSearchQuery(item),
    window,
    scope,
  });
  return `/search?${params.toString()}`;
}
