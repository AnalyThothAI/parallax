import type {
  AssetFlowData,
  AssetFlowRow,
  CurrentMarketSnapshot,
  Decision,
  FactorPoint,
  MarketFieldFact,
  RadarSortMode,
  RiskCap,
  ScoreBlock,
  ScoreContribution,
  TimingBlock,
  TokenFactorSnapshot,
  TokenFlowItem,
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
    { driver: 0, watch: 0, investigate: 0, discard: 0 },
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

export function tokenRadarRowToTokenItem(
  row: AssetFlowRow,
  window: TokenFlowItem["flow"]["window"],
  scope: TokenFlowItem["posts_query"]["scope"],
): TokenFlowItem {
  const snapshot = requiredFactorSnapshot(row);
  const subject = requiredObject(snapshot.subject, "factor_snapshot.subject") as Record<
    string,
    unknown
  >;
  const attentionFamily = requiredFamily(snapshot, "social_attention");
  const qualityFamily = requiredFamily(snapshot, "social_quality");
  const marketFamily = requiredFamily(snapshot, "market_quality");
  const timingFamily = requiredFamily(snapshot, "timing");
  const attention = familyFacts(attentionFamily);
  const qualityFacts = familyFacts(qualityFamily);
  const marketFacts = familyFacts(marketFamily);
  const timingFacts = familyFacts(timingFamily);
  const currentMarket = requiredCurrentMarket(row);
  const marketFields = requiredObject(currentMarket.fields, "current_market.fields") as Record<
    string,
    unknown
  >;
  const priceField =
    marketField(marketFields, "price_usd") ?? marketField(marketFields, "price_quote");
  const marketStatusField = marketField(marketFields, "market_status");
  const marketCapField = marketField(marketFields, "market_cap_usd");
  const liquidityField = marketField(marketFields, "liquidity_usd");
  const holdersField = marketField(marketFields, "holders");
  const volume24hField = marketField(marketFields, "volume_24h_usd");
  const composite = requiredObject(snapshot.composite, "factor_snapshot.composite") as Record<
    string,
    unknown
  >;
  const familyScores = recordValue(composite.family_scores);
  const gates = recordValue(snapshot.hard_gates);
  const provenance = recordValue(snapshot.provenance);
  const mentions5m = requiredNumber(
    attention.mentions_5m,
    "factor_snapshot.social_attention.mentions_5m",
  );
  const mentions1h = requiredNumber(
    attention.mentions_1h,
    "factor_snapshot.social_attention.mentions_1h",
  );
  const mentions4h = requiredNumber(
    attention.mentions_4h,
    "factor_snapshot.social_attention.mentions_4h",
  );
  const mentions24h = requiredNumber(
    attention.mentions_24h,
    "factor_snapshot.social_attention.mentions_24h",
  );
  const mentions = requiredNumber(
    attention[`mentions_${window}`],
    `factor_snapshot.social_attention.mentions_${window}`,
  );
  const authors = requiredNumber(
    attention.unique_authors,
    "factor_snapshot.social_attention.unique_authors",
  );
  const watched = requiredNumber(
    attention.watched_mentions,
    "factor_snapshot.social_attention.watched_mentions",
  );
  const latestSeenMs = requiredNumber(
    attention.latest_seen_ms,
    "factor_snapshot.social_attention.latest_seen_ms",
  );
  const previousMentions = optionalNumber(attention.previous_mentions) ?? 0;
  const mentionDelta = optionalNumber(attention.mention_delta) ?? mentions - previousMentions;
  const mentionDeltaPct = optionalNullableNumber(attention.mention_delta_pct);
  const zScore = optionalNullableNumber(attention.z_score);
  const newBurstScore = optionalNullableNumber(attention.new_burst_score);
  const streamShare = optionalNumber(attention.stream_share) ?? 0;
  const baselineStatus =
    optionalString(attention.baseline_status) ?? String(attentionFamily.data_health ?? "snapshot");
  const baselineSampleCount = optionalNumber(attention.baseline_sample_count) ?? 0;
  const sourceEventIds = requiredStringArray(
    Array.isArray(row.source_event_ids) ? row.source_event_ids : provenance.source_event_ids,
    "factor_snapshot.provenance.source_event_ids",
  );
  const target = row.target ?? {};
  const isChainAsset = target.target_type === "Asset";
  const isSnapshotAsset = subject.target_type === "Asset";
  const isCexToken = subject.target_type === "CexToken" || target.target_type === "CexToken";
  const displaySymbol =
    isChainAsset || isCexToken
      ? (stringValue(subject.symbol) ?? target.symbol ?? null)
      : (row.intent?.display_symbol ?? stringValue(subject.symbol) ?? target.symbol ?? null);
  const targetId =
    stringValue(subject.target_id) ?? target.target_id ?? row.resolution?.target_id ?? null;
  const address = isSnapshotAsset ? (stringValue(subject.address) ?? target.address ?? null) : null;
  const nativeMarketId =
    stringValue(marketFacts.native_market_id) ?? target.native_market_id ?? null;
  const identityKey =
    targetId ??
    row.intent?.intent_id ??
    address ??
    nativeMarketId ??
    displaySymbol ??
    "unknown-token-intent";
  const resolved = Boolean(targetId && subject.target_type);
  const resolutionReasons = row.resolution?.reason_codes ?? row.resolution?.reasons ?? [];
  const candidateCount =
    row.resolution?.candidate_ids?.length ?? row.resolution?.candidates?.length ?? 0;
  const discoveryStatus = discoveryStatusSummary(row.resolution?.discovery);
  const marketStatus =
    optionalString(marketStatusField?.value) ??
    optionalString(currentMarket.market_status) ??
    "missing";
  const marketObservationStatus = marketStatus;
  const marketHasUsableSnapshot = marketStatus === "fresh";
  const priceChangeStatus = priceChangeStatusFromSnapshot(marketStatus, timingFacts);
  const heat = scoreBlockFromFamily(attentionFamily, "social_attention", "social_heat");
  const quality = scoreBlockFromFamily(qualityFamily, "social_quality", "discussion_quality");
  const propagation = scoreBlockFromFamily(qualityFamily, "social_quality", "propagation");
  const tradeability = scoreBlockFromFamily(marketFamily, "market_quality", "tradeability");
  const tradeabilityHardRisks = stringArray(tradeability.hard_risks);
  const timing = scoreBlockFromFamily(timingFamily, "timing", "timing");
  const decision = decisionFromRecommendation(
    optionalString(composite.recommended_decision) ?? optionalString(row.decision),
  );
  const heatStatus =
    optionalString(attention.status) ??
    heatStatusFromScore(heat.score, attentionFamily.data_health);
  const timingStatus = timingStatusFromSnapshot(marketStatus, timing.risks, resolved);
  const chaseRisk =
    timing.risks.includes("chase_risk") || timing.risks.includes("timing_chase_risk");
  const marketPrice = optionalNullableNumber(priceField?.value);
  const marketProvider = firstString(
    priceField?.provider,
    marketCapField?.provider,
    liquidityField?.provider,
    holdersField?.provider,
    volume24hField?.provider,
  );
  const chain = isSnapshotAsset ? (stringValue(subject.chain) ?? target.chain_id ?? null) : null;
  const blockedReasons = requiredStringArray(
    gates.blocked_reasons ?? [],
    "factor_snapshot.hard_gates.blocked_reasons",
  );
  const opportunityScore = requiredNumber(
    composite.rank_score,
    "factor_snapshot.composite.rank_score",
  );
  const opportunity = {
    ...scoreBlockFromComposite(snapshot, blockedReasons),
    decision,
    decision_priority: decision === "driver" ? 3 : decision === "watch" ? 2 : 1,
    hard_risks: blockedReasons,
    components: {
      heat: scoreFromFamilyScores(familyScores, "social_attention", heat.score),
      quality: scoreFromFamilyScores(familyScores, "social_quality", quality.score),
      propagation: scoreFromFamilyScores(familyScores, "social_quality", propagation.score),
      tradeability: scoreFromFamilyScores(familyScores, "market_quality", tradeability.score),
      timing: scoreFromFamilyScores(familyScores, "timing", timing.score),
    },
    score: opportunityScore,
  };
  return {
    identity: {
      identity_key: identityKey,
      identity_status: row.resolution?.status ?? (resolved ? "EXACT" : "NIL"),
      target_type: stringValue(subject.target_type) ?? target.target_type ?? null,
      target_id: targetId,
      asset_id: isChainAsset ? (targetId ?? undefined) : undefined,
      asset_type: stringValue(subject.target_type) ?? target.target_type ?? null,
      venue_type: isCexToken ? "cex" : isSnapshotAsset || isChainAsset ? "dex" : null,
      exchange: isCexToken
        ? (target.provider ??
          marketProvider ??
          stringValue(marketFacts.exchange) ??
          (nativeMarketId ? "okx" : null))
        : null,
      inst_id: isCexToken ? nativeMarketId : null,
      inst_type: isCexToken
        ? (target.feed_type ?? stringValue(marketFacts.feed_type) ?? null)
        : null,
      chain,
      address,
      symbol: displaySymbol,
      resolution_reasons: resolutionReasons,
      lookup_keys: row.resolution?.lookup_keys ?? [],
      candidate_count: candidateCount,
      discovery_status: discoveryStatus,
    },
    market: {
      market_status: marketStatus,
      price: marketPrice,
      price_status: optionalString(priceField?.status),
      market_cap: optionalNullableNumber(marketCapField?.value),
      market_cap_status: optionalString(marketCapField?.status),
      liquidity: optionalNullableNumber(liquidityField?.value),
      liquidity_status: optionalString(liquidityField?.status),
      pool_status: marketHasUsableSnapshot ? "ready" : "missing",
      holder_count: optionalNullableNumber(holdersField?.value),
      holder_count_status: optionalString(holdersField?.status),
      volume_24h: optionalNullableNumber(volume24hField?.value),
      volume_24h_status: optionalString(volume24hField?.status),
      provider: marketProvider,
      snapshot_age_ms: optionalNullableNumber(priceField?.age_ms),
      snapshot_received_at_ms: optionalNullableNumber(priceField?.observed_at_ms),
      social_signal_start_ms: optionalNumber(timingFacts.social_signal_start_ms) ?? latestSeenMs,
      reference_ms: latestSeenMs,
      price_at_social_start: optionalNullableNumber(marketFacts.price_at_social_start),
      price_at_reference: optionalNullableNumber(marketFacts.price_at_reference) ?? marketPrice,
      price_change_since_social_pct: optionalNullableNumber(
        timingFacts.price_change_since_social_pct,
      ),
      price_before_social_start: optionalNullableNumber(marketFacts.price_before_social_start),
      price_change_before_social_pct: optionalNullableNumber(
        timingFacts.price_change_before_social_pct,
      ),
      price_at_first_snapshot: optionalNullableNumber(marketFacts.price_at_first_snapshot),
      first_snapshot_observed_at_ms: optionalNullableNumber(
        marketFacts.first_snapshot_observed_at_ms,
      ),
      price_change_since_first_snapshot_pct: optionalNullableNumber(
        marketFacts.price_change_since_first_snapshot_pct,
      ),
      market_observation_status: marketObservationStatus,
      price_change_status: priceChangeStatus,
    },
    flow: {
      window,
      window_start_ms: null,
      window_end_ms: latestSeenMs,
      mentions,
      direct_mentions: resolved ? mentions : 0,
      symbol_mentions: mentions,
      weighted_mentions: mentions,
      avg_attribution_confidence: row.resolution?.confidence ?? undefined,
      watched_mentions: watched,
      previous_mentions: previousMentions,
      mention_delta: mentionDelta,
      mention_delta_pct: mentionDeltaPct,
      z_score: zScore,
      new_burst_score: newBurstScore,
      stream_dominance: 0,
      baseline_status: baselineStatus,
      baseline_sample_count: baselineSampleCount,
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
      status: heatStatus,
    },
    discussion_quality: {
      ...quality,
      evidence_specificity: 0,
      avg_post_quality: quality.score,
      avg_attribution_confidence: row.resolution?.confidence ?? 0,
      duplicate_text_share: optionalNumber(qualityFacts.duplicate_text_share) ?? 0,
      informative_post_count:
        optionalNumber(qualityFacts.informative_post_count) ??
        Math.min(mentions, authors || mentions),
      watched_source_count: watched,
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
      top_authors: [],
    },
    tradeability: {
      ...tradeability,
      identity_tradeable: Boolean(tradeability.identity_tradeable ?? resolved),
      market_fresh: Boolean(tradeability.market_fresh ?? marketHasUsableSnapshot),
      market_cap_present: Boolean(tradeability.market_cap_present ?? hasFieldValue(marketCapField)),
      liquidity_present: Boolean(tradeability.liquidity_present ?? hasFieldValue(liquidityField)),
      pool_present: Boolean(tradeability.pool_present ?? marketHasUsableSnapshot),
      hard_risks: tradeabilityHardRisks.length ? tradeabilityHardRisks : tradeability.risks,
    },
    timing: {
      score: timing.score,
      score_version: timing.score_version,
      status: timingStatus,
      social_signal_start_ms: optionalNumber(timingFacts.social_signal_start_ms) ?? latestSeenMs,
      price_change_since_social_pct: optionalNullableNumber(
        timingFacts.price_change_since_social_pct,
      ),
      price_change_before_social_pct: optionalNullableNumber(
        timingFacts.price_change_before_social_pct,
      ),
      market_observation_status: marketObservationStatus,
      chase_risk: chaseRisk,
      reasons: timing.reasons,
      risks: timing.risks,
      contributions: timing.contributions,
      risk_caps: timing.risk_caps,
    },
    opportunity,
    watch: {
      status: watched ? "direct_watch" : "public_only",
      direct_mentions: watched,
      direct_authors: watched ? 1 : 0,
      seed_link_count: 0,
      top_seed: null,
      reasons: watched ? ["watched_source_present"] : [],
      risks: watched ? [] : ["no_watched_confirmation"],
    },
    evidence_total_count: sourceEventIds.length,
    posts_query: {
      target_type: stringValue(subject.target_type) ?? target.target_type ?? null,
      target_id: targetId,
      window,
      scope,
      range: "current_window",
    },
    timeline_query: {
      target_type: stringValue(subject.target_type) ?? target.target_type ?? null,
      target_id: targetId,
      window,
      scope,
    },
  };
}

type FactorFamily = TokenFactorSnapshot["families"][string];
type DerivedScoreBlock = ScoreBlock & Record<string, unknown>;

type SnapshotRow = AssetFlowRow & {
  factor_snapshot?: TokenFactorSnapshot;
};

function requiredFactorSnapshot(row: SnapshotRow): TokenFactorSnapshot {
  const snapshot = row.factor_snapshot;
  if (!snapshot || typeof snapshot !== "object") {
    throw new Error("token_radar_contract:factor_snapshot");
  }
  if (snapshot.schema_version !== "token_factor_snapshot_v1") {
    throw new Error("token_radar_contract:factor_snapshot.schema_version");
  }
  return snapshot;
}

function requiredCurrentMarket(row: AssetFlowRow): CurrentMarketSnapshot {
  const currentMarket = row.current_market;
  if (!currentMarket || typeof currentMarket !== "object") {
    throw new Error("token_radar_contract:current_market");
  }
  if (!currentMarket.fields || typeof currentMarket.fields !== "object") {
    throw new Error("token_radar_contract:current_market.fields");
  }
  return currentMarket;
}

function requiredFamily(snapshot: TokenFactorSnapshot, familyName: string): FactorFamily {
  const family = snapshot.families?.[familyName];
  if (!family || typeof family !== "object") {
    throw new Error(`token_radar_contract:factor_snapshot.families.${familyName}`);
  }
  return family;
}

function familyFacts(family: FactorFamily): Record<string, unknown> {
  return recordValue(family.facts);
}

function marketField(fields: Record<string, unknown>, key: string): MarketFieldFact | null {
  const field = fields[key];
  return field && typeof field === "object" && !Array.isArray(field)
    ? (field as MarketFieldFact)
    : null;
}

function scoreBlockFromFamily(
  family: FactorFamily,
  factorFamily: string,
  scoreVersionFamily: string,
): DerivedScoreBlock {
  const score = Math.round(requiredNumber(family.score, `factor_snapshot.${factorFamily}.score`));
  const points = factorPoints(family);
  const risks = uniqueStrings(
    points
      .flatMap((point) => [...stringArray(point.risk_flags), optionalString(point.hard_gate)])
      .filter((item): item is string => Boolean(item)),
  );
  return {
    score,
    score_version: `token_factor_snapshot_v1:${scoreVersionFamily}`,
    reasons: reasonsFromFamily(factorFamily, points, risks),
    risks,
    hard_risks: risks.filter(
      (risk) => risk.includes("block") || risk.includes("below") || risk.includes("missing"),
    ),
    contributions: contributionsFromFactors(points, factorFamily, score),
    risk_caps: riskCapsFromFactors(points),
  };
}

function reasonsFromFamily(factorFamily: string, points: FactorPoint[], risks: string[]): string[] {
  if (factorFamily === "timing") {
    return risks.length ? risks : [];
  }
  if (factorFamily === "social_quality") {
    return ["resolved_asset"];
  }
  if (factorFamily === "market_quality") {
    return ["market_quality_snapshot"];
  }
  return uniqueStrings(points.map((point) => `${point.family}.${point.key}`));
}

function scoreBlockFromComposite(
  snapshot: TokenFactorSnapshot,
  blockedReasons: string[],
): DerivedScoreBlock {
  const composite = requiredObject(snapshot.composite, "factor_snapshot.composite") as Record<
    string,
    unknown
  >;
  const score = Math.round(
    requiredNumber(composite.rank_score, "factor_snapshot.composite.rank_score"),
  );
  return {
    score,
    score_version: "token_factor_snapshot_v1:composite",
    reasons: [optionalString(composite.recommended_decision) ?? "factor_snapshot_composite"],
    risks: blockedReasons,
    hard_risks: blockedReasons,
    contributions: Object.entries(recordValue(composite.family_scores)).map(([feature, value]) => ({
      feature,
      value: optionalNumber(value) ?? 0,
      reason: "factor_family_score",
    })),
    risk_caps: blockedReasons.map((risk) => ({ risk, cap: 39 })),
  };
}
function factorPoints(family: FactorFamily): FactorPoint[] {
  const factors = recordValue(family.factors);
  return Object.values(factors).filter((value): value is FactorPoint =>
    Boolean(value && typeof value === "object"),
  );
}

function contributionsFromFactors(
  points: FactorPoint[],
  fallbackFeature: string,
  fallbackScore: number,
): ScoreContribution[] {
  const contributions = points.map((point) => ({
    feature: `${point.family}.${point.key}`,
    value: optionalNumber(point.score) ?? 0,
    reason: optionalString(point.data_health) ?? "factor_snapshot",
  }));
  return contributions.length
    ? contributions
    : [{ feature: fallbackFeature, value: fallbackScore, reason: "factor_snapshot" }];
}

function riskCapsFromFactors(points: FactorPoint[]): RiskCap[] {
  return points
    .filter((point) => Boolean(point.hard_gate))
    .map((point) => ({
      risk: optionalString(point.hard_gate) ?? `${point.family}.${point.key}`,
      cap: 39,
    }));
}

function scoreFromFamilyScores(
  familyScores: Record<string, unknown>,
  key: string,
  fallback: number,
): number {
  return optionalNumber(familyScores[key]) ?? fallback;
}

function decisionFromRecommendation(value: string | null | undefined): Decision {
  if (
    value === "driver" ||
    value === "high_alert" ||
    value === "alert" ||
    value === "trade_candidate"
  )
    return "driver";
  if (value === "watch" || value === "token_watch") return "watch";
  if (value === "discard" || value === "ignore") return "discard";
  return "investigate";
}

function heatStatusFromScore(score: number, dataHealth: unknown): string {
  if (dataHealth === "missing" || dataHealth === "partial") return String(dataHealth);
  if (score >= 80) return "burst";
  if (score >= 50) return "rising";
  return "cold";
}

function timingStatusFromSnapshot(
  marketStatus: string,
  risks: string[],
  resolved: boolean,
): TimingBlock["status"] {
  if (risks.includes("chase_risk") || risks.includes("timing_chase_risk")) return "chase_risk";
  if (marketStatus === "missing") return resolved ? "market_pending" : "market_unavailable";
  return "neutral";
}

function priceChangeStatusFromSnapshot(
  marketStatus: string,
  timingFacts: Record<string, unknown>,
): string {
  if (marketStatus === "missing") return "missing_market";
  if (
    timingFacts.price_change_since_social_pct === null ||
    timingFacts.price_change_since_social_pct === undefined
  ) {
    return "insufficient_history";
  }
  return "ready";
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value;
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

function requiredArray<T>(value: unknown, field: string): T[] {
  if (!Array.isArray(value)) {
    throw new Error(`token_radar_contract:${field}`);
  }
  return value as T[];
}

function requiredStringArray(value: unknown, field: string): string[] {
  return requiredArray(value, field).map((item) => requiredString(item, field));
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function optionalNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  return optionalNumber(value) ?? null;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    const text = optionalString(value);
    if (text) {
      return text;
    }
  }
  return null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function hasFieldValue(field: MarketFieldFact | null): boolean {
  return field?.value !== null && field?.value !== undefined;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item))
    : [];
}

function uniqueStrings(items: string[]): string[] {
  return Array.from(new Set(items));
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function discoveryStatusSummary(discovery: AssetFlowRow["resolution"]["discovery"]): string | null {
  if (!discovery?.length) {
    return null;
  }
  const statuses = Array.from(new Set(discovery.map((item) => item.status).filter(Boolean)));
  if (statuses.length === 1) {
    const candidateTotal = discovery.reduce(
      (sum, item) => sum + Number(item.candidate_count ?? 0),
      0,
    );
    return candidateTotal > 0 ? `${statuses[0]}:${candidateTotal}` : String(statuses[0]);
  }
  return statuses.join("+");
}
