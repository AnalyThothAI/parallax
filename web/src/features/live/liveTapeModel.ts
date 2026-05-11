import type { LivePayload, TokenFlowItem } from "../../api/types";
import { compactNumber, eventText, formatRelativeTime } from "../../lib/format";

type LiveSignalTapeBase = {
  score?: number | null;
  reason: string;
  body?: string | null;
};

export type LiveSignalTapeItem =
  | (LiveSignalTapeBase & { kind: "event"; payload: LivePayload })
  | (LiveSignalTapeBase & { kind: "token"; token: TokenFlowItem; event?: LivePayload | null });

export function buildLiveSignalTapeItems({
  liveItems,
  tokenItems
}: {
  liveItems: LivePayload[];
  tokenItems: TokenFlowItem[];
}): LiveSignalTapeItem[] {
  const byTargetId = new Map<string, TokenFlowItem>();
  const byCa = new Map<string, TokenFlowItem>();
  const byIdentityKey = new Map<string, TokenFlowItem>();
  const bySymbol = new Map<string, TokenFlowItem[]>();
  for (const item of tokenItems) {
    if (item.identity.target_id) {
      byTargetId.set(item.identity.target_id, item);
    }
    byIdentityKey.set(item.identity.identity_key, item);
    const caKey = tokenCaKey(item.identity.chain, item.identity.address);
    if (caKey) {
      byCa.set(caKey, item);
    }
    const symbol = item.identity.symbol?.toUpperCase();
    if (symbol) {
      bySymbol.set(symbol, [...(bySymbol.get(symbol) ?? []), item]);
    }
  }
  const rows: LiveSignalTapeItem[] = [];
  for (const payload of liveItems) {
    const tokenMatch = tokenMatchForPayload(payload, { byTargetId, byCa, byIdentityKey, bySymbol });
    if (tokenMatch) {
      rows.push({
        kind: "token",
        token: tokenMatch,
        event: payload,
        score: tokenMatch.opportunity.score,
        reason: tokenTapeReason(tokenMatch),
        body: eventText(payload.event) || tokenTapeBody(tokenMatch)
      });
    } else {
      rows.push({
        kind: "event",
        payload,
        score: payload.alerts.length ? 80 : null,
        reason: payload.alerts.length ? "watched alert" : "public pulse",
        body: eventText(payload.event)
      });
    }
  }
  for (const item of tokenItems.slice(0, 8)) {
    rows.push({
      kind: "token",
      token: item,
      event: null,
      score: item.opportunity.score,
      reason: tokenTapeReason(item),
      body: tokenTapeBody(item)
    });
  }
  const seen = new Set<string>();
  return rows.filter((item) => {
    const id = `${item.kind}:${tapeItemId(item)}`;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

export function tapeItemId(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event?.event.event_id ?? item.token.identity.identity_key;
  }
  return item.payload.event.event_id;
}

export function tokenTapeReason(token: TokenFlowItem): string {
  const reason = token.opportunity.reasons[0] ?? token.opportunity.risks[0] ?? token.social_heat.reasons[0];
  return reason ? reason.replaceAll("_", " ") : `${compactNumber(token.social_heat.mentions)} mentions`;
}

function tokenTapeBody(item: TokenFlowItem): string {
  return [
    `${compactNumber(item.social_heat.mentions)} 帖`,
    `Heat ${compactNumber(item.social_heat.score)}`,
    `作者 ${compactNumber(item.propagation.independent_authors)}`,
    item.timing.status === "market_pending" ? "市场观测处理中" : formatRelativeTime(item.flow.window_end_ms)
  ].join(" · ");
}

function tokenMatchForPayload(
  payload: LivePayload,
  lookup: {
    byTargetId: Map<string, TokenFlowItem>;
    byCa: Map<string, TokenFlowItem>;
    byIdentityKey: Map<string, TokenFlowItem>;
    bySymbol: Map<string, TokenFlowItem[]>;
  }
): TokenFlowItem | undefined {
  for (const resolution of payload.token_resolutions ?? []) {
    if (resolution.target_id && lookup.byTargetId.has(resolution.target_id)) {
      return lookup.byTargetId.get(resolution.target_id);
    }
    if (resolution.target_id && lookup.byIdentityKey.has(resolution.target_id)) {
      return lookup.byIdentityKey.get(resolution.target_id);
    }
    if (resolution.intent_id && lookup.byIdentityKey.has(resolution.intent_id)) {
      return lookup.byIdentityKey.get(resolution.intent_id);
    }
  }
  for (const intent of payload.token_intents ?? []) {
    if (intent.intent_id && lookup.byIdentityKey.has(intent.intent_id)) {
      return lookup.byIdentityKey.get(intent.intent_id);
    }
    const symbol = intent.display_symbol?.toUpperCase();
    const symbolMatches = symbol ? lookup.bySymbol.get(symbol) ?? [] : [];
    if (symbolMatches.length === 1) {
      return symbolMatches[0];
    }
    const caKey = tokenCaKey(intent.chain_hint, intent.address_hint);
    if (caKey && lookup.byCa.has(caKey)) {
      return lookup.byCa.get(caKey);
    }
  }
  for (const entity of payload.entities) {
    if (entity.entity_type !== "ca") {
      continue;
    }
    const caKey = tokenCaKey(entity.chain, entity.normalized_value);
    if (caKey && lookup.byCa.has(caKey)) {
      return lookup.byCa.get(caKey);
    }
  }
  const symbol =
    payload.event.cashtags?.[0]?.toUpperCase() ??
    payload.entities.find((entity) => entity.entity_type === "symbol")?.normalized_value?.toUpperCase();
  const symbolMatches = symbol ? lookup.bySymbol.get(symbol) ?? [] : [];
  return symbolMatches.length === 1 ? symbolMatches[0] : undefined;
}

function tokenCaKey(chain?: string | null, address?: string | null): string | null {
  if (!chain || !address) {
    return null;
  }
  return `${chain.toLowerCase()}:${address.toLowerCase()}`;
}
