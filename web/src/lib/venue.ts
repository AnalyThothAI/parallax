import type { SignalPulseItem, TokenFlowItem } from "../api/types";
import { gmgnTokenUrl } from "./gmgn";

export type VenueAction = {
  label: string;
  url: string;
};

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

export function signalPulseVenueActions(item: SignalPulseItem): VenueAction[] {
  const dexAction = signalPulseDexVenueAction(item);
  if (dexAction) {
    return [dexAction];
  }
  const cexAction = signalPulseCexVenueAction(item);
  return cexAction ? [cexAction] : [];
}

function signalPulseDexVenueAction(item: SignalPulseItem): VenueAction | null {
  if (item.target_type !== "Asset") {
    return null;
  }
  const parsed = parseAssetTargetId(item.target_id);
  if (!parsed) {
    return null;
  }
  const url = gmgnTokenUrl(parsed.chain, parsed.address);
  return url ? { label: "GMGN", url } : null;
}

function signalPulseCexVenueAction(item: SignalPulseItem): VenueAction | null {
  if (item.target_type !== "CexToken" && !item.target_id?.startsWith("cex_token:")) {
    return null;
  }
  const market = recordValue(item.market_context_json);
  const pricefeed = parseCexPricefeedId(stringValue(market.pricefeed_id));
  if (pricefeed?.exchange === "okx") {
    return { label: "OKX", url: okxUrl(pricefeed.instId, pricefeed.instType) };
  }
  const symbol = item.symbol?.trim().replace(/^\$/, "").toUpperCase();
  return symbol ? { label: "OKX", url: okxUrl(`${symbol}-USDT`, "SPOT") } : null;
}

function parseAssetTargetId(targetId?: string | null): { chain: string; address: string } | null {
  const parts = targetId?.trim().split(":") ?? [];
  if (parts[0] !== "asset" || parts.length < 4) {
    return null;
  }
  if (parts[1] === "eip155" && parts.length >= 5) {
    return { chain: `eip155:${parts[2]}`, address: parts.at(-1) ?? "" };
  }
  if (parts[1] === "solana") {
    return { chain: "solana", address: parts.at(-1) ?? "" };
  }
  if (parts[1] === "dex" && parts[2]) {
    return { chain: parts[2], address: parts.at(-1) ?? "" };
  }
  return null;
}

function parseCexPricefeedId(pricefeedId?: string | null): { exchange: string; instType: string; instId: string } | null {
  const parts = pricefeedId?.trim().split(":") ?? [];
  if (parts.length < 5 || parts[0] !== "pricefeed" || parts[1] !== "cex") {
    return null;
  }
  return {
    exchange: parts[2].toLowerCase(),
    instType: parts[3].toUpperCase(),
    instId: parts.slice(4).join(":")
  };
}

function cexVenueAction(item: TokenFlowItem): VenueAction | null {
  const exchange = item.identity.exchange?.trim().toLowerCase();
  const instId = item.identity.inst_id?.trim();
  if (!exchange || !instId) {
    return null;
  }
  if (exchange === "okx") {
    return { label: "OKX", url: okxUrl(instId, item.identity.inst_type) };
  }
  if (exchange === "binance") {
    return { label: "Binance", url: binanceUrl(instId, item.identity.inst_type) };
  }
  return null;
}

function okxUrl(instId: string, instType?: string | null): string {
  const slug = instId.trim().toLowerCase();
  const type = instType?.trim().toUpperCase();
  const path = type === "SWAP" || slug.endsWith("-swap") ? "trade-swap" : "trade-spot";
  return `https://www.okx.com/${path}/${slug}`;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
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
