import type { SignalPulseItem, TokenFlowItem } from "@lib/types";

import { gmgnTokenUrl } from "./gmgn";
import { requireTokenFactorSnapshot } from "./tokenFactorSnapshot";

export type VenueAction = {
  label: string;
  url: string;
};

export type TokenRadarVenueFilter = "all" | "sol" | "eth" | "base" | "bsc" | "cex";

export const TOKEN_RADAR_VENUE_FILTERS: Array<{
  key: TokenRadarVenueFilter;
  label: string;
}> = [
  { key: "all", label: "All" },
  { key: "sol", label: "SOL" },
  { key: "eth", label: "ETH" },
  { key: "base", label: "BASE" },
  { key: "bsc", label: "BSC" },
  { key: "cex", label: "CEX" },
];

export function tokenVenueAction(item: TokenFlowItem): VenueAction | null {
  const venueType = item.identity.venue_type?.trim().toLowerCase();
  if (venueType === "cex") {
    return cexVenueAction(item);
  }
  if (venueType === "dex") {
    const url = gmgnTokenUrl(item.identity.chain, item.identity.address);
    return url ? { label: "GMGN", url } : null;
  }
  return null;
}

export function tokenRadarVenueKey(
  item: TokenFlowItem,
): Exclude<TokenRadarVenueFilter, "all"> | null {
  const venueType = item.identity.venue_type?.trim().toLowerCase();
  if (venueType === "cex" || item.identity.target_type === "CexToken") {
    return "cex";
  }
  return chainVenueKey(item.identity.chain);
}

export function tokenVenueDisplayLabel(item: TokenFlowItem): string | null {
  const venueType = item.identity.venue_type?.trim().toLowerCase();
  if (venueType === "cex" || item.identity.target_type === "CexToken") {
    return "CEX";
  }
  return chainDisplayLabel(item.identity.chain);
}

export function chainDisplayLabel(chain?: string | null): string | null {
  const key = chainVenueKey(chain);
  if (key) {
    return TOKEN_RADAR_VENUE_FILTERS.find((item) => item.key === key)?.label ?? key.toUpperCase();
  }
  const text = chain?.trim();
  return text ? text.toUpperCase() : null;
}

export function signalPulseVenueActions(item: SignalPulseItem): VenueAction[] {
  const dexAction = signalPulseDexVenueAction(item);
  if (dexAction) {
    return [dexAction];
  }
  const cexAction = signalPulseCexVenueAction(item);
  return cexAction ? [cexAction] : [];
}

function chainVenueKey(
  chain?: string | null,
): Exclude<TokenRadarVenueFilter, "all" | "cex"> | null {
  const normalized = chain?.trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (normalized === "sol" || normalized === "solana") {
    return "sol";
  }
  if (normalized === "eth" || normalized === "ethereum" || normalized === "eip155:1") {
    return "eth";
  }
  if (normalized === "base" || normalized === "eip155:8453") {
    return "base";
  }
  if (
    normalized === "bsc" ||
    normalized === "bnb" ||
    normalized === "bnb_chain" ||
    normalized === "eip155:56"
  ) {
    return "bsc";
  }
  return null;
}

function signalPulseDexVenueAction(item: SignalPulseItem): VenueAction | null {
  const subject = requireTokenFactorSnapshot(item.factor_snapshot).subject;
  const chain = subject.chain;
  const address = subject.address;
  if (!chain || !address) {
    return null;
  }
  const targetType = subject.target_type ?? item.target_type;
  if (targetType !== "Asset") {
    return null;
  }
  const url = gmgnTokenUrl(chain, address);
  return url ? { label: "GMGN", url } : null;
}

function signalPulseCexVenueAction(item: SignalPulseItem): VenueAction | null {
  const subject = requireTokenFactorSnapshot(item.factor_snapshot).subject;
  const targetType = subject.target_type ?? item.target_type;
  const targetId = subject.target_id ?? item.target_id;
  if (
    targetType !== "CexToken" &&
    !targetId?.startsWith("cex_token:") &&
    !targetId?.includes(":cex:")
  ) {
    return null;
  }
  const nativeMarketId = stringValue(subject.pricefeed_id) ?? targetId;
  const pricefeed = parseCexPricefeedId(nativeMarketId);
  if (pricefeed?.exchange === "okx") {
    return { label: "OKX", url: okxUrl(pricefeed.instId, pricefeed.instType) };
  }
  const parsedTarget = parseCexTargetId(nativeMarketId);
  if (parsedTarget?.exchange === "okx") {
    return { label: "OKX", url: okxUrl(parsedTarget.instId, parsedTarget.instType) };
  }
  const symbol = (subject.symbol ?? item.symbol)?.trim().replace(/^\$/, "").toUpperCase();
  return symbol ? { label: "OKX", url: okxUrl(`${symbol}-USDT`, "SPOT") } : null;
}

function parseCexPricefeedId(
  pricefeedId?: string | null,
): { exchange: string; instType: string; instId: string } | null {
  const parts = pricefeedId?.trim().split(":") ?? [];
  if (parts.length < 5 || parts[0] !== "pricefeed" || parts[1] !== "cex") {
    return null;
  }
  return {
    exchange: parts[2].toLowerCase(),
    instType: parts[3].toUpperCase(),
    instId: parts.slice(4).join(":"),
  };
}

function parseCexTargetId(
  targetId?: string | null,
): { exchange: string; instType: string; instId: string } | null {
  const parts = targetId?.trim().split(":") ?? [];
  if (parts.length < 4 || parts[0] !== "asset" || parts[1] !== "cex") {
    return null;
  }
  return {
    exchange: parts[2].toLowerCase(),
    instType: parts.at(-1)?.toUpperCase().endsWith("-SWAP") ? "SWAP" : "SPOT",
    instId: parts.slice(3).join(":"),
  };
}

function cexVenueAction(item: TokenFlowItem): VenueAction | null {
  const parsedPricefeed = parseCexPricefeedId(item.identity.inst_id);
  const parsedTarget = parseCexTargetId(item.identity.inst_id);
  const exchange =
    normalizeCexExchange(item.identity.exchange) ??
    parsedPricefeed?.exchange ??
    parsedTarget?.exchange;
  const instId = parsedPricefeed?.instId ?? parsedTarget?.instId ?? item.identity.inst_id?.trim();
  const instType =
    normalizeCexInstType(item.identity.inst_type) ??
    parsedPricefeed?.instType ??
    parsedTarget?.instType;
  if (!exchange || !instId) {
    return null;
  }
  if (exchange === "okx") {
    return { label: "OKX", url: okxUrl(instId, instType) };
  }
  if (exchange === "binance") {
    return { label: "Binance", url: binanceUrl(instId, instType) };
  }
  return null;
}

function normalizeCexExchange(value?: string | null): string | null {
  const text = value?.trim().toLowerCase();
  if (!text) {
    return null;
  }
  if (text === "okx" || text === "okx_cex") {
    return "okx";
  }
  if (text === "binance" || text === "binance_cex") {
    return "binance";
  }
  return text;
}

function normalizeCexInstType(value?: string | null): string | null {
  const text = value?.trim().toUpperCase();
  if (!text) {
    return null;
  }
  if (text === "CEX_SPOT") {
    return "SPOT";
  }
  if (text === "CEX_SWAP" || text === "PERP" || text === "PERPETUAL") {
    return "SWAP";
  }
  return text;
}

function okxUrl(instId: string, instType?: string | null): string {
  const slug = instId.trim().toLowerCase();
  const type = instType?.trim().toUpperCase();
  const path = type === "SWAP" || slug.endsWith("-swap") ? "trade-swap" : "trade-spot";
  return `https://www.okx.com/${path}/${slug}`;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function binanceUrl(instId: string, instType?: string | null): string {
  const normalized = instId.trim().toUpperCase();
  const type = instType?.trim().toUpperCase();
  if (type === "SWAP" || normalized.endsWith("-SWAP")) {
    return `https://www.binance.com/en/futures/${normalized.replace(/-SWAP$/, "").replaceAll("-", "")}`;
  }
  return `https://www.binance.com/en/trade/${normalized.replace("-", "_")}`;
}
