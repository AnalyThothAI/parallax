import type { TokenFlowItem } from "../api/types";
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

function binanceUrl(instId: string, instType?: string | null): string {
  const normalized = instId.trim().toUpperCase();
  const type = instType?.trim().toUpperCase();
  if (type === "SWAP" || normalized.endsWith("-SWAP")) {
    return `https://www.binance.com/en/futures/${normalized.replace(/-SWAP$/, "").replaceAll("-", "")}`;
  }
  return `https://www.binance.com/en/trade/${normalized.replace("-", "_")}`;
}
