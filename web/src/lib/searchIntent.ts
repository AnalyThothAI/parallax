import type { TokenFlowItem } from "../api/types";

export function tokenForSearchQuery(query: string, items: TokenFlowItem[]): TokenFlowItem | null {
  const text = query.trim();
  if (!text || text.startsWith("@") || /\s/.test(text)) {
    return null;
  }

  const tokenIdentityMatch = uniqueMatch(items, (item) => {
    const normalized = text.toLowerCase();
    return (
      item.identity.token_id?.toLowerCase() === normalized ||
      item.identity.identity_key.toLowerCase() === normalized ||
      item.identity.address?.toLowerCase() === normalized
    );
  });
  if (tokenIdentityMatch) {
    return tokenIdentityMatch;
  }

  const chainAddress = chainAddressQuery(text);
  if (chainAddress) {
    const [chain, address] = chainAddress;
    return uniqueMatch(
      items,
      (item) => item.identity.chain?.toLowerCase() === chain && item.identity.address?.toLowerCase() === address
    );
  }

  const symbol = symbolQuery(text);
  if (!symbol) {
    return null;
  }
  return uniqueMatch(items, (item) => item.identity.symbol?.toUpperCase() === symbol);
}

function uniqueMatch(items: TokenFlowItem[], predicate: (item: TokenFlowItem) => boolean): TokenFlowItem | null {
  const matches = items.filter(predicate);
  return matches.length === 1 ? matches[0] : null;
}

function chainAddressQuery(text: string): [string, string] | null {
  const separator = text.indexOf(":");
  if (separator <= 0) {
    return null;
  }
  const chain = text.slice(0, separator).trim().toLowerCase();
  const address = text.slice(separator + 1).trim().toLowerCase();
  return chain && address ? [chain, address] : null;
}

function symbolQuery(text: string): string | null {
  const raw = text.startsWith("$") ? text.slice(1) : text;
  if (!/^[A-Za-z][A-Za-z0-9_]{1,20}$/.test(raw)) {
    return null;
  }
  return raw.toUpperCase();
}
