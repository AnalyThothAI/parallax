import type { NewsItemDetail, NewsRow } from "@shared/model/newsIntel";

export type NewsInstrument = {
  label: string;
  priceState: string;
  primary?: boolean;
  type: string;
  use: string;
};

export const newsKind = (item: Pick<NewsRow, "fact_lanes" | "headline" | "summary">): string => {
  const text = lower(
    [item.headline, item.summary, ...(item.fact_lanes ?? []).map((fact) => fact.event_type)].join(
      " ",
    ),
  );
  if (text.includes("hack") || text.includes("exploit") || text.includes("admin key"))
    return "risk";
  if (
    text.includes("sec") ||
    text.includes("fed") ||
    text.includes("law") ||
    text.includes("regulat")
  )
    return "policy";
  if (
    text.includes("bitcoin") ||
    text.includes("btc") ||
    text.includes("ether") ||
    text.includes("eth") ||
    text.includes("etf")
  ) {
    return "market";
  }
  if ((item.fact_lanes ?? []).length) return "market";
  return "context";
};

export const newsMarketQuestion = (item: Pick<NewsRow, "headline">): string => {
  const headline = lower(item.headline);
  if (headline.includes("world liberty") || headline.includes("wlfi")) {
    return "Does this spill into WLFI liquidity and narrative risk?";
  }
  if (headline.includes("echo") || headline.includes("ebtc") || headline.includes("exploit")) {
    return "Which liquid market is exposed: eBTC, Monad, collateral lenders, or no listed target?";
  }
  if (headline.includes("sec") || headline.includes("regulat") || headline.includes("law")) {
    return "Does this change venue access, issuer risk, or only long-horizon backdrop?";
  }
  if (
    headline.includes("bitcoin") ||
    headline.includes("btc") ||
    headline.includes("ether") ||
    headline.includes("eth")
  ) {
    return "Is this broad beta pressure or a specific flow catalyst?";
  }
  return "What tradable asset, venue, or risk bucket does this move?";
};

export const newsMarketRead = (
  item: Pick<NewsRow, "fact_lanes" | "headline" | "summary" | "token_lanes">,
): string => {
  const headline = lower(item.headline);
  if (hasResolvedTokenLane(item)) {
    return "Token identity is linked, so this can route into downstream trading context after fact acceptance.";
  }
  if (headline.includes("world liberty") || headline.includes("wlfi")) {
    return "Solvency warning around a WLFI-linked treasury vehicle. Potential narrative risk, but no production tradable target is resolved yet.";
  }
  if (headline.includes("echo") || headline.includes("ebtc") || headline.includes("exploit")) {
    return "Exploit story around Echo/eBTC. Useful for risk monitoring after affected protocol, chain, and liquid exposure are resolved.";
  }
  if (headline.includes("sec") && headline.includes("tokenized")) {
    return "SEC tokenized-stock headline may affect RWA venues and compliance narratives; current row has no direct token route.";
  }
  if (headline.includes("bitcoin") || headline.includes("btc")) {
    return "BTC beta pressure item. Treat as market regime context unless paired with flow, liquidation, or derivatives confirmation.";
  }
  if (headline.includes("ether") || headline.includes("eth")) {
    return "ETH treasury or accumulation context. Useful for major-asset narrative, not a direct microcap signal.";
  }
  if ((item.fact_lanes ?? []).some((fact) => fact.event_type === "hack")) {
    return "Security event. Resolve affected asset or protocol before it can route into tradeable risk.";
  }
  if ((item.fact_lanes ?? []).some((fact) => fact.event_type === "regulatory")) {
    return "Regulatory event. Keep in policy backdrop until an affected asset, venue, or issuer is linked.";
  }
  return (
    item.summary ||
    "Context item. Keep searchable and attach later if it joins a deeper market story."
  );
};

export const newsRouteState = (item: Pick<NewsRow, "fact_lanes" | "token_lanes">): string => {
  if (hasResolvedTokenLane(item)) return "token linked";
  if ((item.token_lanes ?? []).length || (item.fact_lanes ?? []).length) return "identity missing";
  return "context only";
};

export const newsNextAction = (
  item: Pick<NewsRow, "fact_lanes" | "headline" | "summary" | "token_lanes">,
): string => {
  if (hasResolvedTokenLane(item) && (item.fact_lanes ?? []).length) return "Attach market reaction";
  if ((item.fact_lanes ?? []).length) return "Resolve target identity";
  if (newsKind(item) === "market") return "Watch confirming flow";
  return "Keep searchable";
};

export const inferNewsInstruments = (
  item: Pick<NewsItemDetail, "headline" | "summary" | "token_lanes">,
): NewsInstrument[] => {
  const rawHeadline = String(item.headline ?? "");
  const headline = lower(`${rawHeadline} ${item.summary ?? ""}`);
  const instruments: NewsInstrument[] = (item.token_lanes ?? []).map((lane) => ({
    label: lane.symbol || lane.target_id || "linked token",
    priceState: isResolvedTokenLane(lane) ? "market route available" : "identity unresolved",
    primary: isResolvedTokenLane(lane),
    type: lane.target_type || "token",
    use: isResolvedTokenLane(lane)
      ? "Downstream Token Radar context once fact is accepted."
      : "Observed token text; resolve production identity before treating this as a quote route.",
  }));
  const add = (instrument: NewsInstrument) => {
    if (!instruments.some((candidate) => lower(candidate.label) === lower(instrument.label))) {
      instruments.push(instrument);
    }
  };
  if (headline.includes("world liberty") || headline.includes("wlfi")) {
    add({
      label: "WLFI",
      priceState: "price missing",
      primary: true,
      type: "token / narrative",
      use: "Check whether solvency noise leaks into WLFI liquidity or narrative beta.",
    });
    add({
      label: "AI Financial",
      priceState: "quote missing",
      type: "issuer / stock",
      use: "Map SEC filing entity to issuer profile before treating this as equity risk.",
    });
    add({
      label: "BTC / ETH beta",
      priceState: "reaction missing",
      type: "crypto majors",
      use: "Use only if broad beta reacts while story propagates.",
    });
  }
  if (headline.includes("echo") || headline.includes("ebtc") || headline.includes("exploit")) {
    add({
      label: "eBTC",
      priceState: "price missing",
      primary: true,
      type: "token / wrapped asset",
      use: "Primary affected asset candidate from headline.",
    });
    add({
      label: "WBTC",
      priceState: "reaction missing",
      type: "collateral asset",
      use: "Monitor borrow/collateral stress if linked by official or onchain source.",
    });
    add({
      label: "Monad",
      priceState: "basket missing",
      type: "ecosystem / chain",
      use: "Potential ecosystem risk bucket, not a direct trade without liquid target.",
    });
  }
  if (headline.includes("sec") && headline.includes("tokenized")) {
    add({
      label: "Tokenized stocks",
      priceState: "basket missing",
      primary: true,
      type: "theme basket",
      use: "Regime headline for RWA and tokenized equity venues.",
    });
    add({
      label: "Securitize",
      priceState: "quote missing",
      type: "venue / issuer",
      use: "Useful for venue map, not a direct token route here.",
    });
  }
  for (const match of rawHeadline.matchAll(/\(([A-Z]{2,6})\)/g)) {
    add({
      label: match[1],
      priceState: "quote missing",
      primary: true,
      type: "stock ticker",
      use: "Link to stock quote and sector context before trade use.",
    });
  }
  if (!instruments.length) {
    add({
      label: "No mapped instrument",
      priceState: "price context missing",
      type: "data gap",
      use: "Keep as reading/search context until extraction finds a tradable target.",
    });
  }
  return instruments;
};

export const newsInstrumentLabel = (
  item: Pick<NewsItemDetail, "headline" | "summary" | "token_lanes">,
): string =>
  inferNewsInstruments(item)
    .slice(0, 3)
    .map((instrument) => instrument.label)
    .join(" / ");

export const newsPriceState = (
  item: Pick<NewsItemDetail, "headline" | "summary" | "token_lanes">,
): string => {
  const states = inferNewsInstruments(item).map((instrument) => lower(instrument.priceState));
  if (states.some((state) => state.includes("available"))) return "price route available";
  if (states.some((state) => state.includes("unresolved"))) return "identity unresolved";
  if (states.some((state) => state.includes("quote"))) return "quote missing";
  if (states.some((state) => state.includes("reaction"))) return "reaction missing";
  return "price context missing";
};

function lower(value: unknown): string {
  return String(value ?? "").toLowerCase();
}

function hasResolvedTokenLane(item: Pick<NewsRow, "token_lanes">): boolean {
  return (item.token_lanes ?? []).some(isResolvedTokenLane);
}

function isResolvedTokenLane(lane: {
  lane?: string | null;
  resolution_status?: string | null;
  target_id?: string | null;
}): boolean {
  return Boolean(
    lane.target_id || lane.lane === "resolved" || lane.resolution_status === "resolved",
  );
}
