import type {
  AssetFlowData,
  AssetFlowRow,
  Decision,
  RadarSortMode,
  RiskCap,
  ScoreContribution,
  TimingBlock,
  TokenFlowItem
} from "../api/types";

export function sortTokenItems(items: TokenFlowItem[], mode: RadarSortMode): TokenFlowItem[] {
  const copy = [...items];
  return copy.sort((a, b) => sortValue(b, mode) - sortValue(a, mode));
}

function sortValue(item: TokenFlowItem, mode: RadarSortMode): number {
  if (mode === "heat") return item.social_heat.score;
  if (mode === "quality") return item.discussion_quality.score;
  if (mode === "propagation") return item.propagation.score;
  if (mode === "timing") return (item.timing.chase_risk ? -1000 : 0) + item.timing.score;
  return item.opportunity.score;
}

export function countDecisions(items: TokenFlowItem[]): Record<Decision, number> {
  return items.reduce<Record<Decision, number>>(
    (counts, item) => {
      counts[item.opportunity.decision] += 1;
      return counts;
    },
    { driver: 0, watch: 0, investigate: 0, discard: 0 }
  );
}

export function assetFlowRows(data?: AssetFlowData | null): AssetFlowRow[] {
  if (!data) {
    return [];
  }
  return [...data.targets, ...data.attention];
}

export function tokenRadarItems(
  data: AssetFlowData | null | undefined,
  window: TokenFlowItem["flow"]["window"],
  scope: TokenFlowItem["posts_query"]["scope"],
): TokenFlowItem[] {
  if (!data) {
    return [];
  }
  return assetFlowRows(data).map((row) => tokenRadarRowToTokenItem(row, window, scope));
}

export function tokenRadarRowToTokenItem(row: AssetFlowRow, window: TokenFlowItem["flow"]["window"], scope: TokenFlowItem["posts_query"]["scope"]): TokenFlowItem {
  const attention = row.attention as unknown as Record<string, unknown>;
  const mentions = requiredNumber(row.attention.mentions_window, "attention.mentions_window");
  const authors = requiredNumber(row.attention.unique_authors, "attention.unique_authors");
  const watched = requiredNumber(row.attention.watched_mentions, "attention.watched_mentions");
  const latestSeenMs = requiredNumber(row.attention.latest_seen_ms, "attention.latest_seen_ms");
  const previousMentions = requiredNumber(row.attention.previous_mentions, "attention.previous_mentions");
  const mentionDelta = requiredNumber(row.attention.mention_delta, "attention.mention_delta");
  const mentionDeltaPct = requiredNullableNumber(attention, "mention_delta_pct", "attention.mention_delta_pct");
  const zScore = requiredNullableNumber(attention, "z_score", "attention.z_score");
  const newBurstScore = requiredNullableNumber(attention, "new_burst_score", "attention.new_burst_score");
  const streamShare = requiredNumber(row.attention.stream_share, "attention.stream_share");
  const baselineStatus = requiredString(row.attention.baseline_status, "attention.baseline_status");
  const baselineSampleCount = requiredNumber(row.attention.baseline_sample_count, "attention.baseline_sample_count");
  const mentions5m = requiredNumber(row.attention.mentions_5m, "attention.mentions_5m");
  const mentions1h = requiredNumber(row.attention.mentions_1h, "attention.mentions_1h");
  const mentions4h = requiredNumber(row.attention.mentions_4h, "attention.mentions_4h");
  const mentions24h = requiredNumber(row.attention.mentions_24h, "attention.mentions_24h");
  const sourceEventIds = requiredArray(row.source_event_ids, "source_event_ids");
  const resolved = isResolvedResolutionStatus(row.resolution.status);
  const price = requiredObject(row.price, "price");
  const target = row.target ?? {};
  const isChainAsset = target.target_type === "Asset";
  const isCexToken = target.target_type === "CexToken";
  const displaySymbol = isChainAsset || isCexToken
    ? target.symbol ?? null
    : row.intent?.display_symbol ?? target.symbol ?? null;
  const targetId = target.target_id ?? row.resolution.target_id ?? null;
  const identityKey = targetId ?? row.intent?.intent_id ?? target.address ?? target.native_market_id ?? displaySymbol ?? "unknown-token-intent";
  const resolutionReasons = row.resolution.reason_codes ?? row.resolution.reasons ?? [];
  const candidateCount = row.resolution.candidate_ids?.length ?? row.resolution.candidates?.length ?? 0;
  const discoveryStatus = discoveryStatusSummary(row.resolution.discovery);
  const marketObservationStatus = requiredString(price.market_observation_status, "price.market_observation_status");
  const marketStatus = requiredString(price.market_status, "price.market_status");
  const marketHasUsableSnapshot = marketStatus === "fresh";
  const priceChangeStatus = requiredString(price.price_change_status, "price.price_change_status");
  const heat = normalizedScoreBlock(row.score?.heat, "heat");
  const quality = normalizedScoreBlock(row.score?.quality, "quality");
  const propagation = normalizedScoreBlock(row.score?.propagation, "propagation");
  const tradeability = normalizedScoreBlock(row.score?.tradeability, "tradeability");
  const timing = normalizedScoreBlock(row.score?.timing, "timing");
  const opportunity = normalizedScoreBlock(row.score?.opportunity, "opportunity");
  const decision = normalizeDecision(row.decision);
  const heatStatus = requiredString(heat.status, "score.heat.status");
  const timingStatus = normalizeTimingStatus(timing.status ?? timing.reasons[0], resolved);
  const chaseRisk = Boolean(timing.chase_risk ?? timing.hard_risks?.includes("chase_risk") ?? timing.risks.includes("chase_risk"));
  const marketPrice = price.price_usd ?? price.price_quote ?? null;
  const chain = isChainAsset ? target.chain_id ?? null : null;
  const address = isChainAsset ? target.address ?? null : null;
  return {
    identity: {
      identity_key: identityKey,
      identity_status: row.resolution.status,
      target_type: target.target_type ?? null,
      target_id: targetId,
      asset_id: isChainAsset ? targetId ?? undefined : undefined,
      asset_type: target.target_type ?? null,
      venue_type: isCexToken ? "cex" : isChainAsset ? "dex" : null,
      exchange: isCexToken ? target.provider ?? null : null,
      inst_id: isCexToken ? target.native_market_id ?? null : null,
      inst_type: isCexToken ? target.feed_type ?? null : null,
      chain,
      address,
      symbol: displaySymbol,
      resolution_reasons: resolutionReasons,
      lookup_keys: row.resolution.lookup_keys ?? [],
      candidate_count: candidateCount,
      discovery_status: discoveryStatus
    },
    market: {
      market_status: marketStatus,
      price: marketPrice,
      market_cap: price.market_cap_usd ?? null,
      liquidity: price.liquidity_usd ?? null,
      pool_status: marketHasUsableSnapshot ? "ready" : "missing",
      holder_count: price.holders ?? null,
      volume_24h: price.volume_24h_usd ?? null,
      snapshot_age_ms: price.snapshot_age_ms ?? null,
      snapshot_received_at_ms: price.snapshot_observed_at_ms ?? null,
      social_signal_start_ms: price.social_signal_start_ms ?? latestSeenMs,
      reference_ms: latestSeenMs,
      price_at_social_start: price.price_at_social_start ?? null,
      price_at_reference: price.price_at_reference ?? marketPrice,
      price_change_since_social_pct: price.price_change_since_social_pct ?? null,
      price_before_social_start: price.price_before_social_start ?? null,
      price_change_before_social_pct: price.price_change_before_social_pct ?? null,
      price_at_first_snapshot: price.price_at_first_snapshot ?? null,
      first_snapshot_observed_at_ms: price.first_snapshot_observed_at_ms ?? null,
      price_change_since_first_snapshot_pct: price.price_change_since_first_snapshot_pct ?? null,
      market_observation_status: marketObservationStatus,
      price_change_status: priceChangeStatus
    },
    flow: {
      window,
      window_start_ms: null,
      window_end_ms: latestSeenMs,
      mentions,
      direct_mentions: resolved ? mentions : 0,
      symbol_mentions: mentions,
      weighted_mentions: mentions,
      avg_attribution_confidence: row.resolution.confidence ?? undefined,
      watched_mentions: watched,
      previous_mentions: previousMentions,
      mention_delta: mentionDelta,
      mention_delta_pct: mentionDeltaPct,
      z_score: zScore,
      new_burst_score: newBurstScore,
      stream_dominance: 0,
      baseline_status: baselineStatus,
      baseline_sample_count: baselineSampleCount
    },
    social_heat: {
      ...heat,
      window,
      mentions,
      mentions_5m: mentions5m,
      mentions_1h: mentions1h,
      mentions_4h: mentions4h,
      mentions_24h: mentions24h,
      weighted_mentions: mentions,
      previous_mentions: previousMentions,
      mention_delta: mentionDelta,
      mention_delta_pct: mentionDeltaPct,
      z_score: zScore,
      new_burst_score: newBurstScore,
      stream_share: streamShare,
      watched_share: mentions ? watched / mentions : 0,
      status: heatStatus
    },
    discussion_quality: {
      ...quality,
      evidence_specificity: 0,
      avg_post_quality: quality.score,
      avg_attribution_confidence: row.resolution.confidence ?? 0,
      duplicate_text_share: 0,
      informative_post_count: Math.min(mentions, authors || mentions),
      watched_source_count: watched
    },
    propagation: {
      ...propagation,
      independent_authors: authors,
      effective_authors: authors,
      new_authors: authors,
      top_author_share: authors ? 1 / authors : 0,
      duplicate_text_share: 0,
      author_entropy: authors > 1 ? 1 : 0,
      reproduction_rate: null,
      phase: authors >= 3 ? "expansion" : authors >= 2 ? "ignition" : "seed",
      top_authors: []
    },
    tradeability: {
      ...tradeability,
      identity_tradeable: Boolean(tradeability.identity_tradeable ?? resolved),
      market_fresh: Boolean(tradeability.market_fresh ?? marketHasUsableSnapshot),
      market_cap_present: Boolean(tradeability.market_cap_present ?? price.market_cap_usd),
      liquidity_present: Boolean(tradeability.liquidity_present ?? price.liquidity_usd),
      pool_present: Boolean(tradeability.pool_present ?? marketHasUsableSnapshot),
      hard_risks: tradeability.hard_risks ?? tradeability.risks
    },
    timing: {
      score: timing.score,
      score_version: timing.score_version,
      status: timingStatus,
      social_signal_start_ms: latestSeenMs,
      price_change_since_social_pct: price.price_change_since_social_pct ?? null,
      price_change_before_social_pct: price.price_change_before_social_pct ?? null,
      market_observation_status: marketObservationStatus,
      chase_risk: chaseRisk,
      reasons: timing.reasons,
      risks: timing.risks,
      contributions: timing.contributions,
      risk_caps: timing.risk_caps
    },
    opportunity: {
      ...opportunity,
      decision,
      decision_priority: decision === "driver" ? 3 : decision === "watch" ? 2 : 1,
      hard_risks: opportunity.hard_risks ?? opportunity.risks,
      components: {
        heat: requiredNumber(row.score.opportunity.components.heat, "score.opportunity.components.heat"),
        quality: requiredNumber(row.score.opportunity.components.quality, "score.opportunity.components.quality"),
        propagation: requiredNumber(row.score.opportunity.components.propagation, "score.opportunity.components.propagation"),
        tradeability: requiredNumber(row.score.opportunity.components.tradeability, "score.opportunity.components.tradeability"),
        timing: requiredNumber(row.score.opportunity.components.timing, "score.opportunity.components.timing")
      }
    },
    watch: {
      status: watched ? "direct_watch" : "public_only",
      direct_mentions: watched,
      direct_authors: watched ? 1 : 0,
      seed_link_count: 0,
      top_seed: null,
      reasons: watched ? ["watched_source_present"] : [],
      risks: watched ? [] : ["no_watched_confirmation"]
    },
    evidence_total_count: sourceEventIds.length,
    posts_query: { target_type: target.target_type ?? null, target_id: targetId, window, scope, range: "current_window" },
    timeline_query: { target_type: target.target_type ?? null, target_id: targetId, window, scope }
  };
}

function isResolvedResolutionStatus(status?: string | null): boolean {
  return status === "EXACT" || status === "UNIQUE_BY_CONTEXT";
}

type RadarScoreInput = {
  score?: number | null;
  score_version?: string | null;
  reasons?: string[];
  risks?: string[];
  hard_risks?: string[];
  contributions?: ScoreContribution[];
  risk_caps?: RiskCap[];
  status?: string | null;
  chase_risk?: boolean | null;
};

function normalizedScoreBlock(block: RadarScoreInput | undefined, component: string): any {
  if (!block || typeof block !== "object") {
    throw new Error(`token_radar_contract:score.${component}`);
  }
  const extra = { ...block };
  return {
    ...extra,
    score: Math.round(requiredNumber(block.score, `score.${component}.score`)),
    score_version: requiredString(block.score_version, `score.${component}.score_version`),
    reasons: requiredStringArray(block.reasons, `score.${component}.reasons`),
    risks: requiredStringArray(block.risks, `score.${component}.risks`),
    hard_risks: Array.isArray(block.hard_risks) ? block.hard_risks : [],
    contributions: requiredNonEmptyArray(block.contributions, `score.${component}.contributions`),
    risk_caps: requiredArray(block.risk_caps, `score.${component}.risk_caps`),
    status: block.status ?? undefined,
    chase_risk: block.chase_risk ?? undefined
  };
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value;
}

function requiredNullableNumber(record: Record<string, unknown>, key: string, field: string): number | null {
  if (!(key in record)) {
    throw new Error(`token_radar_contract:${field}`);
  }
  const value = record[key];
  if (value === null) {
    return null;
  }
  return requiredNumber(value, field);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value;
}

function requiredObject<T extends object>(value: T | null | undefined, field: string): T {
  if (!value || typeof value !== "object") {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value;
}

function requiredArray<T>(value: T[] | undefined, field: string): T[] {
  if (!Array.isArray(value)) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value;
}

function requiredNonEmptyArray<T>(value: T[] | undefined, field: string): T[] {
  const items = requiredArray(value, field);
  if (!items.length) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return items;
}

function requiredStringArray(value: string[] | undefined, field: string): string[] {
  return requiredArray(value, field).map((item) => requiredString(item, field));
}

function normalizeDecision(value: string | null | undefined): Decision {
  return value === "driver" || value === "watch" || value === "investigate" || value === "discard" ? value : "investigate";
}

function normalizeTimingStatus(value: string | null | undefined, resolved: boolean): TimingBlock["status"] {
  if (value === "neutral" || value === "market_pending" || value === "market_unavailable" || value === "chase_risk") {
    return value;
  }
  return resolved ? "neutral" : "market_unavailable";
}

function discoveryStatusSummary(discovery: AssetFlowRow["resolution"]["discovery"]): string | null {
  if (!discovery?.length) {
    return null;
  }
  const statuses = Array.from(new Set(discovery.map((item) => item.status).filter(Boolean)));
  if (statuses.length === 1) {
    const candidateTotal = discovery.reduce((sum, item) => sum + Number(item.candidate_count ?? 0), 0);
    return candidateTotal > 0 ? `${statuses[0]}:${candidateTotal}` : String(statuses[0]);
  }
  return statuses.join("+");
}
