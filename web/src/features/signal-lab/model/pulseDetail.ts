import {
  compactNumber,
  formatRelativeAge,
  formatUsdCompact,
  formatUtcTimestamp,
  formatTokenPriceUsd,
  shortAddress,
} from "@lib/format";
import type {
  SignalPulseItem,
  SignalPulseStagePayload,
  SignalPulseStages,
  SocialEventDetail,
  TokenFactorFamily,
  TokenFactorFamilyKey,
} from "@lib/types";
import type { TokenCasePostEvent, TokenCaseTone } from "@shared/model/tokenCaseViewModel";
import {
  buildTokenPostEventMarket,
  cleanText,
  normalizeTokenSymbol,
} from "@shared/model/tokenPostEvent";

export const GATE_AGENT_MISMATCH_CONFIDENCE = 0.5;

const HISTOGRAM_BUCKETS = 24;
const HISTOGRAM_SPAN_MS = 24 * 60 * 60 * 1000;
const BURST_WINDOW_MS = 12 * 60 * 1000;
const BURST_PRE_WINDOW_MS = 30 * 60 * 1000;
const LATEST_WINDOW_MS = 10 * 60 * 1000;
const AUTHOR_SPAM_FOLLOWER_MAX = 5_000;
const AUTHOR_SPAM_SHARE_MIN = 0.3;
const AUTHOR_KOL_FOLLOWER_MIN = 10_000;
const LIQ_WARN_MAX = 50_000;
const VOL_MCAP_RISK_RATIO = 5;

export type Tone = "opportunity" | "health" | "info" | "risk" | "agent" | "neutral" | "warn";
export type DetailDensity = "full" | "compact";

export type Pill = { id: string; label: string; tone: Tone };
export type FreshnessRow = { label: string; value: string; tone: Tone };
export type BurstBin = { startMs: number; endMs: number; count: number };
export type BurstHistogram = {
  bins: BurstBin[];
  firstEventAt: number | null;
  peakBucketIndex: number;
  peakAt: number | null;
  nowAt: number;
  uniqueAuthors: number;
};
export type TimelineNode = {
  kind: "market_anchor" | "first" | "peak" | "now";
  title: string;
  timestampLabel: string;
  relativeAgeLabel: string;
  meta: string;
  tone: Tone;
};
export type FactorFamilyBreakdownRow = { label: string; value: string; tone: Tone };
export type FactorFamilyView = {
  id: TokenFactorFamilyKey;
  name: string;
  score: number;
  scoreTone: Tone;
  rankLabel: string;
  dataHealth: string;
  breakdown: FactorFamilyBreakdownRow[];
};
export type MarketMetric = {
  id: "price" | "mcap" | "liq" | "vol_24h" | "holders";
  label: string;
  value: string;
  subValue: string | null;
  tone: Tone;
};
export type EvidenceAuthorTag = "watched" | "spam_suspect" | "kol_signal" | "normal";
export type EvidenceRow = {
  eventId: string;
  timestampMs: number;
  timestampLabel: string;
  handle: string;
  displayName: string;
  followers: number | null;
  channel: string;
  action: string;
  body: string | null;
  isEmptyBody: boolean;
  cited: boolean;
  authorTag: EvidenceAuthorTag;
  cohortPosition: string | null;
  canonicalUrl: string | null;
};
export type EvidenceGroupId = "earlier" | "burst_window" | "post_burst" | "latest";
export type EvidenceGroup = {
  id: EvidenceGroupId;
  title: string;
  rangeLabel: string;
  defaultExpanded: boolean;
  rows: EvidenceRow[];
  citedCount: number;
  uniqueAuthors: number;
};
export type EvidenceAuthorChip = {
  handle: string;
  postCount: number;
  authorTag: EvidenceAuthorTag;
};
export type AuthorConcentrationSegment = {
  handle: string;
  count: number;
  share: number;
  tone: Tone;
};
export type AuthorConcentrationBar = {
  segments: AuthorConcentrationSegment[];
  topAuthorShare: number;
};
export type EvidenceView = {
  totalCount: number;
  citedCount: number;
  totalUniqueAuthors: number;
  authorChips: EvidenceAuthorChip[];
  groups: EvidenceGroup[];
  timelineItems: TokenCasePostEvent[];
  concentration: AuthorConcentrationBar;
  abstainCallout: string | null;
};
export type InvestigatorView = {
  status: string;
  latencyMs: number | null;
  summary: string;
};
export type DecisionMakerView = {
  status: string;
  latencyMs: number | null;
  summary: string;
};
export type LegacyStageView = {
  stageName: "analyst" | "critic" | "judge";
  status: string;
  latencyMs: number | null;
  summary: string;
};
export type StageRailItem =
  | { kind: "investigator"; status: string; latencyMs: number | null; summary: string }
  | { kind: "decision_maker"; status: string; latencyMs: number | null; summary: string }
  | {
      kind: "legacy";
      stageName: "analyst" | "critic" | "judge";
      status: string;
      latencyMs: number | null;
      summary: string;
    };
export type ResearchOnlyGateView = { status: string; abstainReason: string } | null;
export type GateAgentMismatch = { gateLabel: string; agentLabel: string; note: string } | null;
export type DecisionViewSide = {
  strength: string;
  thesis: string;
  supportingEventIds: string[];
};
export type DecisionSurfaceView = {
  route: string;
  recommendation: string;
  confidenceLabel: string;
  narrative: { archetype: string; thesis: string } | null;
  bull: DecisionViewSide | null;
  bear: DecisionViewSide | null;
  playbook: {
    monitoringHorizon: string;
    watchSignals: string[];
    exitTriggers: string[];
  } | null;
  evidenceLinks: Array<{ eventId: string; url: string }>;
};
export type ReplayMeta = {
  pulseVersion: string;
  gateVersion: string;
  promptVersion: string;
  schemaVersion: string;
  runId: string;
  candidateId: string;
  agentRunId: string;
};
export type AgentRailView = {
  kind: "stages" | "research_only";
  totalLatencyMs: number;
  model: string;
  mismatch: GateAgentMismatch;
  decisionSurface: DecisionSurfaceView | null;
  railItems: StageRailItem[];
  isLegacy: boolean;
  hasLegacyStages: boolean;
  researchOnlyGate: ResearchOnlyGateView;
  replay: ReplayMeta;
};
export type PulseDetailViewModel = {
  candidateId: string;
  hero: {
    subject: { symbol: string; chain: string; shortAddress: string; targetMarketType: string };
    pills: Pill[];
    candidateIdShort: string;
    burstHistogram: BurstHistogram;
    freshness: FreshnessRow[];
  };
  timeline: { nodes: TimelineNode[] };
  families: FactorFamilyView[];
  market: { metrics: MarketMetric[]; staleNotice: string | null };
  evidence: EvidenceView;
  agent: AgentRailView;
};
export type BuildPulseDetailViewInput = {
  item: SignalPulseItem;
  sourceEvents: SocialEventDetail[];
  now: number;
};

export function buildPulseDetailView({
  item,
  now,
  sourceEvents,
}: BuildPulseDetailViewInput): PulseDetailViewModel {
  const events = [...sourceEvents].sort((left, right) => left.timestamp_ms - right.timestamp_ms);
  const burst = buildBurst(events, now);
  const evidence = buildEvidence(item, events, burst);
  const agent = buildAgent(item);
  const topAuthorHandle =
    evidence.concentration.segments[0]?.share && evidence.concentration.segments[0].share >= 0.3
      ? evidence.concentration.segments[0].handle
      : null;
  return {
    candidateId: item.candidate_id,
    hero: buildHero(item, burst, agent, now),
    timeline: { nodes: buildTimeline(item, burst, now) },
    families: buildFamilies(item, topAuthorHandle),
    market: buildMarket(item),
    evidence,
    agent,
  };
}

function buildHero(
  item: SignalPulseItem,
  burst: BurstHistogram,
  agent: AgentRailView,
  now: number,
): PulseDetailViewModel["hero"] {
  const subject = item.factor_snapshot.subject;
  const pills: Pill[] = [
    {
      id: "score_band",
      label: scoreBandLabel(item.score_band),
      tone: scoreBandTone(item.score_band),
    },
  ];
  if (item.decision.route) {
    pills.push({ id: "route", label: `${item.decision.route} 路由`, tone: "info" });
  }
  if (agent.mismatch) {
    pills.push({ id: "gate_agent_mismatch", label: "策略门 ↔ Agent 失谐", tone: "risk" });
  }
  if (
    !item.factor_snapshot.market.event_anchor ||
    item.factor_snapshot.market.readiness.latest_status === "stale"
  ) {
    pills.push({ id: "market_data_stale", label: "市场数据陈旧", tone: "risk" });
  }
  return {
    subject: {
      symbol: `$${(subject.symbol ?? item.symbol ?? item.subject_key).replace(/^\$+/, "")}`,
      chain: subject.chain ?? "",
      shortAddress: shortAddress(subject.address ?? subject.target_id ?? null),
      targetMarketType: subject.target_market_type ?? "",
    },
    pills,
    candidateIdShort: shortenId(item.candidate_id),
    burstHistogram: burst,
    freshness: buildFreshness(item, now),
  };
}

function buildFreshness(item: SignalPulseItem, now: number): FreshnessRow[] {
  const { data_health: dataHealth, market, normalization } = item.factor_snapshot;
  const rows: FreshnessRow[] = [
    {
      label: "identity",
      value: String(dataHealth.identity ?? "-"),
      tone: dataHealth.identity === "ready" ? "health" : "risk",
    },
    {
      label: "social",
      value: String(dataHealth.social ?? "-"),
      tone: dataHealth.social === "ready" ? "health" : "risk",
    },
    {
      label: "event_anchor",
      value: market.event_anchor ? "ready" : "missing",
      tone: market.event_anchor ? "health" : "risk",
    },
  ];
  if (market.decision_latest?.observed_at_ms) {
    rows.push({
      label: "decision_latest",
      value: `${market.readiness.latest_status ?? "ready"} ${formatRelativeAge(
        market.decision_latest.observed_at_ms,
        now,
      )}`,
      tone: market.readiness.latest_status === "stale" ? "warn" : "health",
    });
  } else {
    rows.push({ label: "decision_latest", value: "missing", tone: "risk" });
  }
  rows.push({
    label: "cohort",
    value:
      normalization.cohort_size != null
        ? `${String(normalization.status ?? "ranked")} · ${normalization.cohort_size}`
        : String(normalization.status ?? "-"),
    tone: normalization.status === "ranked" ? "health" : "warn",
  });
  if (normalization.alpha_rank != null) {
    rows.push({
      label: "alpha rank",
      value: `${normalization.alpha_rank.toFixed(3)} · top ${Math.max(
        1,
        Math.round((1 - normalization.alpha_rank) * 100),
      )}%`,
      tone: "info",
    });
  }
  return rows;
}

function buildBurst(events: SocialEventDetail[], now: number): BurstHistogram {
  const bucketMs = HISTOGRAM_SPAN_MS / HISTOGRAM_BUCKETS;
  const startMs = now - HISTOGRAM_SPAN_MS;
  const bins: BurstBin[] = Array.from({ length: HISTOGRAM_BUCKETS }, (_, index) => ({
    startMs: startMs + index * bucketMs,
    endMs: startMs + (index + 1) * bucketMs,
    count: 0,
  }));
  for (const event of events) {
    if (event.timestamp_ms < startMs || event.timestamp_ms > now) {
      continue;
    }
    const index = Math.min(
      HISTOGRAM_BUCKETS - 1,
      Math.floor((event.timestamp_ms - startMs) / bucketMs),
    );
    bins[index].count += 1;
  }
  const peakBucketIndex = bins.reduce(
    (best, bin, index) => (bin.count > bins[best].count ? index : best),
    0,
  );
  return {
    bins,
    firstEventAt: events[0]?.timestamp_ms ?? null,
    peakBucketIndex,
    peakAt: bins[peakBucketIndex].count > 0 ? bins[peakBucketIndex].startMs + bucketMs / 2 : null,
    nowAt: now,
    uniqueAuthors: new Set(events.map((event) => event.author_handle).filter(Boolean)).size,
  };
}

function buildTimeline(item: SignalPulseItem, burst: BurstHistogram, now: number): TimelineNode[] {
  const latest = item.factor_snapshot.market.decision_latest;
  const nodes: TimelineNode[] = [];
  if (latest?.observed_at_ms) {
    nodes.push({
      kind: "market_anchor",
      title: "市场锚点 (decision_latest)",
      timestampLabel: formatUtcTimestamp(latest.observed_at_ms),
      relativeAgeLabel: formatRelativeAge(latest.observed_at_ms, now),
      meta: `市值 ${formatUsdCompact(latest.market_cap_usd)} · 流动性 ${formatUsdCompact(
        latest.liquidity_usd,
      )} · 持仓 ${compactNumber(latest.holders)} · 24h 成交 ${formatUsdCompact(
        latest.volume_24h_usd,
      )}`,
      tone: item.factor_snapshot.market.readiness.latest_status === "stale" ? "risk" : "health",
    });
  }
  if (burst.firstEventAt) {
    nodes.push({
      kind: "first",
      title: "首次提及",
      timestampLabel: formatUtcTimestamp(burst.firstEventAt),
      relativeAgeLabel: formatRelativeAge(burst.firstEventAt, now),
      meta: "捕获到第一条 source event",
      tone: "neutral",
    });
  }
  if (burst.peakAt) {
    nodes.push({
      kind: "peak",
      title: "爆发峰值",
      timestampLabel: formatUtcTimestamp(burst.peakAt),
      relativeAgeLabel: formatRelativeAge(burst.peakAt, now),
      meta: `${burst.bins[burst.peakBucketIndex].count} 条 / 小时 · 共 ${burst.uniqueAuthors} 位独立作者`,
      tone: "opportunity",
    });
  }
  nodes.push({
    kind: "now",
    title: "Pulse 决策落地",
    timestampLabel: formatUtcTimestamp(item.updated_at_ms),
    relativeAgeLabel: formatRelativeAge(item.updated_at_ms, now),
    meta: `${item.decision.stage_count ?? 0} 阶段 · ${
      item.decision.recommendation ?? "-"
    } · 置信度 ${formatConfidence(item.decision.confidence)}`,
    tone: "health",
  });
  return nodes;
}

function buildFamilies(item: SignalPulseItem, topAuthorHandle: string | null): FactorFamilyView[] {
  const order: TokenFactorFamilyKey[] = [
    "social_heat",
    "social_propagation",
    "semantic_catalyst",
    "timing_risk",
  ];
  const names: Record<TokenFactorFamilyKey, string> = {
    social_heat: "社交热度",
    social_propagation: "传播",
    semantic_catalyst: "语义催化",
    timing_risk: "时机 / 风险",
  };
  return order.map((id) =>
    buildFamily(
      id,
      names[id],
      item.factor_snapshot.families[id],
      item.factor_snapshot.normalization.factor_ranks?.[id],
      item.factor_snapshot.normalization.cohort_size,
      item.factor_snapshot.market.readiness.dex_floor_status ?? null,
      topAuthorHandle,
    ),
  );
}

function buildFamily(
  id: TokenFactorFamilyKey,
  name: string,
  family: TokenFactorFamily,
  rank: unknown,
  cohortSize: number | null | undefined,
  dexFloorStatus: string | null,
  topAuthorHandle: string | null,
): FactorFamilyView {
  const facts = family.facts;
  const dataHealth = family.data_health ?? "missing";
  const breakdown: FactorFamilyBreakdownRow[] = [];
  if (id === "social_heat") {
    breakdown.push(
      {
        label: "mentions 1h / 4h / 24h",
        value: `${num(facts.mentions_1h)} · ${num(facts.mentions_4h)} · ${num(facts.mentions_24h)}`,
        tone: "neutral",
      },
      { label: "unique authors", value: String(num(facts.unique_authors)), tone: "neutral" },
      {
        label: "attention surprise",
        value:
          typeof facts.new_burst_score === "number"
            ? `${facts.new_burst_score.toFixed(2)} (baseline n=${num(facts.baseline_sample_count)})`
            : "n/a",
        tone: num(facts.baseline_sample_count) < 10 ? "warn" : "neutral",
      },
      {
        label: "watched seed mentions",
        value: String(num(facts.watched_mentions)),
        tone: num(facts.watched_mentions) > 0 ? "health" : "neutral",
      },
    );
  }
  if (id === "social_propagation") {
    const topAuthorShare = typeof facts.top_author_share === "number" ? facts.top_author_share : 0;
    const topAuthorTone: Tone =
      topAuthorShare >= 0.7 ? "risk" : topAuthorShare >= 0.5 ? "warn" : "neutral";
    const topAuthorSuffix = topAuthorHandle ? ` ← @${topAuthorHandle}` : "";
    const duplicateShare =
      typeof facts.duplicate_text_share === "number" ? facts.duplicate_text_share : null;
    const watchedCount = num(facts.watched_author_count);
    breakdown.push(
      {
        label: "independent authors",
        value: String(num(facts.independent_authors)),
        tone: "neutral",
      },
      {
        label: "time to 2nd / 3rd author",
        value: `${msToHuman(numOrNull(facts.time_to_second_author_ms))} · ${msToHuman(
          numOrNull(facts.time_to_third_author_ms),
        )}`,
        tone: "neutral",
      },
      {
        label: "top author share",
        value: `${topAuthorShare.toFixed(2)}${topAuthorSuffix}`,
        tone: topAuthorTone,
      },
      {
        label: "duplicate text share",
        value: duplicateShare != null ? duplicateShare.toFixed(2) : "n/a",
        tone: duplicateShare != null && duplicateShare >= 0.3 ? "warn" : "neutral",
      },
      {
        label: "watched / kol authors",
        value: String(watchedCount),
        tone: watchedCount > 0 ? "health" : "neutral",
      },
    );
  }
  if (id === "semantic_catalyst") {
    breakdown.push(
      {
        label: "llm covered mentions",
        value: `${num(facts.llm_covered_mentions)} / ${num(facts.mentions)}`,
        tone: num(facts.llm_covered_mentions) === 0 ? "risk" : "neutral",
      },
      {
        label: "direction mix",
        value: dataHealth === "missing" ? "n/a (missing)" : "see raw",
        tone: dataHealth === "missing" ? "risk" : "neutral",
      },
      {
        label: "impact / novelty",
        value: dataHealth === "missing" ? "n/a (missing)" : "see raw",
        tone: dataHealth === "missing" ? "risk" : "neutral",
      },
    );
  }
  if (id === "timing_risk") {
    breakdown.push(
      {
        label: "price change before social",
        value:
          typeof facts.price_change_before_social_pct === "number"
            ? `${facts.price_change_before_social_pct.toFixed(2)}%`
            : "n/a (price feed stale)",
        tone: typeof facts.price_change_before_social_pct === "number" ? "neutral" : "risk",
      },
      {
        label: "price change since social",
        value:
          typeof facts.price_change_since_social_pct === "number"
            ? `${facts.price_change_since_social_pct.toFixed(2)}%`
            : "n/a",
        tone: typeof facts.price_change_since_social_pct === "number" ? "neutral" : "risk",
      },
      {
        label: "dex floor",
        value: dexFloorStatus ?? "unknown",
        tone:
          dexFloorStatus === "ready" || dexFloorStatus === "passed"
            ? "health"
            : dexFloorStatus
              ? "warn"
              : "neutral",
      },
    );
  }
  return {
    id,
    name,
    score: Math.round(family.score ?? 0),
    scoreTone: id === "timing_risk" ? "risk" : family.score >= 70 ? "health" : "info",
    rankLabel:
      typeof rank === "number"
        ? `cohort rank ${rank.toFixed(2)} · top ${Math.max(1, Math.round((1 - rank) * 100))}%`
        : dataHealth === "missing"
          ? "data_health: missing"
          : `cohort size ${cohortSize ?? 0}`,
    dataHealth,
    breakdown,
  };
}

function buildMarket(item: SignalPulseItem): PulseDetailViewModel["market"] {
  const anchor = item.factor_snapshot.market.event_anchor;
  const latest = item.factor_snapshot.market.decision_latest;
  const readiness = item.factor_snapshot.market.readiness;
  const price = anchor?.price_usd ?? latest?.price_usd ?? null;
  const priceStatus = anchor?.price_usd != null ? readiness.anchor_status : readiness.latest_status;
  const marketCap = latest?.market_cap_usd ?? null;
  const liquidity = latest?.liquidity_usd ?? null;
  const volume = latest?.volume_24h_usd ?? null;
  const holders = latest?.holders ?? null;
  const volRatio = marketCap && volume ? volume / marketCap : null;
  const metrics: MarketMetric[] = [
    {
      id: "price",
      label: anchor?.price_usd != null ? "提及价格" : "最新价格",
      value: formatTokenPriceUsd(price),
      subValue: priceStatus ? priceStatus.replaceAll("_", " ") : null,
      tone: priceStatus === "ready" || priceStatus === "live" ? "health" : "warn",
    },
    {
      id: "mcap",
      label: "市值",
      value: formatUsdCompact(marketCap),
      subValue: null,
      tone: "neutral",
    },
    {
      id: "liq",
      label: liquidity != null && liquidity < LIQ_WARN_MAX ? "流动性 · 偏薄" : "流动性",
      value: formatUsdCompact(liquidity),
      subValue: null,
      tone: liquidity != null && liquidity < LIQ_WARN_MAX ? "warn" : "neutral",
    },
    {
      id: "vol_24h",
      label: "24h 成交",
      value: formatUsdCompact(volume),
      subValue:
        volRatio != null && volRatio >= VOL_MCAP_RISK_RATIO ? `${volRatio.toFixed(1)}× 市值` : null,
      tone: volRatio != null && volRatio >= VOL_MCAP_RISK_RATIO ? "risk" : "neutral",
    },
    {
      id: "holders",
      label: "持仓数",
      value: compactNumber(holders),
      subValue: null,
      tone: "neutral",
    },
  ];
  const stale = [];
  if (!item.factor_snapshot.market.event_anchor) {
    stale.push("event_anchor 为空");
  }
  if (readiness.latest_status === "stale") {
    stale.push("decision_latest 陈旧");
  }
  if (readiness.stale_fields.length) {
    stale.push(`stale_fields: [${readiness.stale_fields.join(", ")}]`);
  }
  return { metrics, staleNotice: stale.length ? stale.join(" · ") : null };
}

function buildEvidence(
  item: SignalPulseItem,
  events: SocialEventDetail[],
  burst: BurstHistogram,
): EvidenceView {
  const citedSet = new Set(
    item.decision.evidence_event_ids?.length
      ? item.decision.evidence_event_ids
      : item.evidence_event_ids,
  );
  const authorCounts = new Map<string, number>();
  for (const event of events) {
    const handle = event.author_handle ?? "(unknown)";
    authorCounts.set(handle, (authorCounts.get(handle) ?? 0) + 1);
  }
  const rows = events.map((event, index): EvidenceRow => {
    const handle = event.author_handle ?? "(unknown)";
    const postCount = authorCounts.get(handle) ?? 1;
    const authorShare = events.length ? postCount / events.length : 0;
    const authorTag = classifyAuthor(event, authorShare);
    return {
      eventId: event.event_id,
      timestampMs: event.timestamp_ms,
      timestampLabel: formatUtcTimestamp(event.timestamp_ms),
      handle,
      displayName: event.author_name ?? handle,
      followers: event.author_followers,
      channel: event.channel,
      action: event.action,
      body: event.text_clean,
      isEmptyBody: !event.text_clean,
      cited: citedSet.has(event.event_id),
      authorTag,
      cohortPosition:
        postCount >= 2 ? `${authorRunIndex(events, event, index)}/${postCount}` : null,
      canonicalUrl: event.canonical_url ?? null,
    };
  });
  const groups = bucketGroups(rows, burst, item.updated_at_ms);
  const uniqueAuthors = authorCounts.size;
  const timelineItems = groups.flatMap((group) =>
    group.rows.map((row) => evidenceRowToTimelineItem(item, row, evidencePhase(group.id))),
  );
  return {
    totalCount: events.length,
    citedCount: rows.filter((row) => row.cited).length,
    totalUniqueAuthors: uniqueAuthors,
    authorChips:
      uniqueAuthors > 1
        ? [...authorCounts.entries()]
            .sort((left, right) => right[1] - left[1])
            .slice(0, 5)
            .map(([handle, postCount]) => ({
              handle,
              postCount,
              authorTag: rows.find((row) => row.handle === handle)?.authorTag ?? "normal",
            }))
        : [],
    groups,
    timelineItems,
    concentration: buildConcentration(rows, authorCounts),
    abstainCallout:
      item.decision.recommendation === "abstain"
        ? "agent abstained - showing all source events for context"
        : null,
  };
}

function bucketGroups(
  rows: EvidenceRow[],
  burst: BurstHistogram,
  updatedAtMs: number,
): EvidenceGroup[] {
  const peak = burst.peakAt ?? burst.firstEventAt ?? updatedAtMs;
  const burstStart = peak - BURST_PRE_WINDOW_MS;
  const burstEnd = peak + BURST_WINDOW_MS;
  const latestStart = updatedAtMs - LATEST_WINDOW_MS;
  const raw: Record<EvidenceGroupId, EvidenceRow[]> = {
    earlier: [],
    burst_window: [],
    post_burst: [],
    latest: [],
  };
  for (const row of rows) {
    if (row.timestampMs < burstStart) {
      raw.earlier.push(row);
    } else if (row.timestampMs <= burstEnd) {
      raw.burst_window.push(row);
    } else if (row.timestampMs <= latestStart) {
      raw.post_burst.push(row);
    } else {
      raw.latest.push(row);
    }
  }
  const titles: Record<EvidenceGroupId, string> = {
    earlier: "早期事件",
    burst_window: "爆发窗口",
    post_burst: "后续传播",
    latest: "最新",
  };
  return (Object.keys(raw) as EvidenceGroupId[])
    .filter((id) => raw[id].length > 0)
    .map((id) => {
      const groupRows = raw[id];
      const first = groupRows[0].timestampMs;
      const last = groupRows[groupRows.length - 1].timestampMs;
      return {
        id,
        title: titles[id],
        rangeLabel: `${formatUtcTimestamp(first, { suffix: false })} ~ ${formatUtcTimestamp(last, {
          suffix: false,
        })} UTC`,
        defaultExpanded: id === "burst_window" || id === "latest" || groupRows.length <= 5,
        rows: groupRows,
        citedCount: groupRows.filter((row) => row.cited).length,
        uniqueAuthors: new Set(groupRows.map((row) => row.handle)).size,
      };
    });
}

function evidenceRowToTimelineItem(
  item: SignalPulseItem,
  row: EvidenceRow,
  phase: string,
): TokenCasePostEvent {
  const symbol =
    normalizeTokenSymbol(item.factor_snapshot.subject.symbol) ??
    normalizeTokenSymbol(item.symbol) ??
    normalizeTokenSymbol(item.subject_key);
  const market = pulseEvidenceMarket(item);
  const authorLabel = formatAuthorTag(row.authorTag);
  return {
    id: row.eventId,
    handle: row.handle,
    text: row.body || "（空转发 / 引用，无正文）",
    url: row.canonicalUrl,
    timestampMs: row.timestampMs,
    timeLabel: row.timestampLabel,
    phase,
    role: formatAction(row.action),
    isWatched: row.authorTag === "watched",
    pills: uniqueTimelinePills([
      symbol ? { label: `$${symbol}`, tone: "opportunity" } : null,
      row.cited ? { label: "agent cited", tone: "agent" } : null,
      { label: formatAction(row.action), tone: row.action === "tweet" ? "health" : "info" },
      { label: authorLabel, tone: toneForAuthorTag(row.authorTag) as TokenCaseTone },
      row.followers != null
        ? { label: `${compactNumber(row.followers)} followers`, tone: "neutral" }
        : null,
    ]),
    market,
    quality: {
      score: null,
      scoreLabel: "source event",
      reasons: [],
      contributions: [],
    },
  };
}

function pulseEvidenceMarket(item: SignalPulseItem): TokenCasePostEvent["market"] {
  const market = item.factor_snapshot.market;
  const anchor = market.event_anchor;
  if (anchor?.price_usd != null) {
    return buildTokenPostEventMarket({
      fallbackProvider: "event anchor",
      priceUsd: anchor.price_usd,
      provider: cleanText(anchor.provider),
      providerPrefix: "anchor",
      status: market.readiness.anchor_status,
    });
  }
  const latest = market.decision_latest;
  return buildTokenPostEventMarket({
    fallbackProvider: "decision latest",
    priceUsd: latest?.price_usd,
    provider: cleanText(latest?.provider),
    providerPrefix: "latest",
    status: market.readiness.latest_status,
  });
}

function evidencePhase(id: EvidenceGroupId): string {
  switch (id) {
    case "earlier":
      return "early";
    case "burst_window":
      return "burst";
    case "post_burst":
      return "post-burst";
    case "latest":
      return "latest";
  }
}

function uniqueTimelinePills(
  values: Array<{ label: string; tone: TokenCaseTone } | null>,
): TokenCasePostEvent["pills"] {
  const seen = new Set<string>();
  const pills: TokenCasePostEvent["pills"] = [];
  for (const value of values) {
    if (!value || seen.has(value.label)) {
      continue;
    }
    seen.add(value.label);
    pills.push(value);
  }
  return pills;
}

function buildConcentration(
  rows: EvidenceRow[],
  authorCounts: Map<string, number>,
): AuthorConcentrationBar {
  const segments = [...authorCounts.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([handle, count]) => {
      const sample = rows.find((row) => row.handle === handle);
      return {
        handle,
        count,
        share: rows.length ? count / rows.length : 0,
        tone: toneForAuthorTag(sample?.authorTag ?? "normal"),
      };
    });
  return { segments, topAuthorShare: segments[0]?.share ?? 0 };
}

function buildAgent(item: SignalPulseItem): AgentRailView {
  const stages = item.stages ?? emptyStages();
  const kind = item.decision.route === "research_only" ? "research_only" : "stages";
  const investigator = stages.investigator ?? null;
  const decisionMaker = stages.decision_maker ?? null;
  const hasV2 = Boolean(investigator || decisionMaker);
  const legacyStages: Array<{
    stageName: "analyst" | "critic" | "judge";
    payload: SignalPulseStagePayload;
  }> = [];
  if (stages.analyst) legacyStages.push({ stageName: "analyst", payload: stages.analyst });
  if (stages.critic) legacyStages.push({ stageName: "critic", payload: stages.critic });
  if (stages.judge) legacyStages.push({ stageName: "judge", payload: stages.judge });
  const hasLegacyStages = legacyStages.length > 0;
  const isLegacy = !hasV2 && hasLegacyStages;

  const railItems: StageRailItem[] = [];
  if (kind !== "research_only") {
    if (hasV2) {
      if (investigator) {
        railItems.push({
          kind: "investigator",
          status: investigator.status ?? "skipped",
          latencyMs: investigator.latency_ms ?? null,
          summary: stagePreviewSummary(investigator),
        });
      }
      if (decisionMaker) {
        railItems.push({
          kind: "decision_maker",
          status: decisionMaker.status ?? "skipped",
          latencyMs: decisionMaker.latency_ms ?? null,
          summary: stagePreviewSummary(decisionMaker),
        });
      }
    }
    if (hasLegacyStages) {
      for (const { stageName, payload } of legacyStages) {
        railItems.push({
          kind: "legacy",
          stageName,
          status: payload.status ?? "skipped",
          latencyMs: payload.latency_ms ?? null,
          summary: "历史 v1 响应体未解析；仅保留 stage 审计元数据。",
        });
      }
    }
  }

  const totalLatencyMs =
    (investigator?.latency_ms ?? 0) +
    (decisionMaker?.latency_ms ?? 0) +
    legacyStages.reduce((sum, entry) => sum + (entry.payload.latency_ms ?? 0), 0);
  const model =
    decisionMaker?.model ??
    investigator?.model ??
    legacyStages[legacyStages.length - 1]?.payload.model ??
    legacyStages[0]?.payload.model ??
    "-";

  return {
    kind,
    totalLatencyMs,
    model,
    mismatch: detectMismatch(item),
    decisionSurface: buildDecisionSurface(item),
    railItems,
    isLegacy,
    hasLegacyStages,
    researchOnlyGate:
      kind === "research_only" && stages.research_only_gate
        ? {
            status: stages.research_only_gate.status ?? "ok",
            abstainReason:
              stringValue(record(stages.research_only_gate.response).abstain_reason) ??
              item.decision.abstain_reason ??
              "",
          }
        : null,
    replay: {
      pulseVersion: item.pulse_version ?? "-",
      gateVersion: item.gate_version ?? "-",
      promptVersion: item.prompt_version ?? "-",
      schemaVersion: item.schema_version ?? "-",
      runId: item.agent_run_id ?? "-",
      candidateId: item.candidate_id,
      agentRunId: item.agent_run_id ?? "-",
    },
  };
}

function buildDecisionSurface(item: SignalPulseItem): DecisionSurfaceView | null {
  const decision = item.decision;
  const narrativeArchetype = stringValue(decision.narrative_archetype) ?? "";
  const narrativeThesis = stringValue(decision.narrative_thesis_zh) ?? "";
  const narrative =
    narrativeArchetype || narrativeThesis
      ? { archetype: narrativeArchetype || "—", thesis: narrativeThesis || "—" }
      : null;
  const bull = buildDecisionSide(decision.bull_view);
  const bear = buildDecisionSide(decision.bear_view);
  const playbook = buildDecisionPlaybook(decision.playbook);
  const evidenceLinks = Object.entries(decision.evidence_event_urls ?? {})
    .filter((entry): entry is [string, string] => Boolean(entry[0] && entry[1]))
    .map(([eventId, url]) => ({ eventId, url }));

  if (!narrative && !bull && !bear && !playbook && evidenceLinks.length === 0) {
    return null;
  }

  return {
    route: stringValue(decision.route) ?? "—",
    recommendation: stringValue(decision.recommendation) ?? "—",
    confidenceLabel: formatConfidence(decision.confidence),
    narrative,
    bull,
    bear,
    playbook,
    evidenceLinks,
  };
}

function buildDecisionSide(value: unknown): DecisionViewSide | null {
  const payload = record(value);
  const strength = stringValue(payload.strength) ?? "";
  const thesis = stringValue(payload.thesis_zh) ?? "";
  const supportingEventIds = stringList(payload.supporting_event_ids);
  if ((!strength && !thesis && supportingEventIds.length === 0) || strength === "absent") {
    return null;
  }
  return {
    strength: strength || "—",
    thesis: thesis || "—",
    supportingEventIds,
  };
}

function buildDecisionPlaybook(value: unknown): DecisionSurfaceView["playbook"] {
  const payload = record(value);
  if (payload.has_playbook !== true) {
    return null;
  }
  const monitoringHorizon = stringValue(payload.monitoring_horizon) ?? "";
  const watchSignals = stringList(payload.watch_signals);
  const exitTriggers = stringList(payload.exit_triggers);
  if (!monitoringHorizon && watchSignals.length === 0 && exitTriggers.length === 0) {
    return null;
  }
  return {
    monitoringHorizon: monitoringHorizon || "—",
    watchSignals,
    exitTriggers,
  };
}

function stagePreviewSummary(stage: SignalPulseStagePayload): string {
  const response = record(stage.response);
  const summary =
    stringValue(response.summary_zh) ??
    stringValue(response.summary) ??
    stringValue(response.recommendation) ??
    stringValue(stage.error);
  return summary ?? "—";
}

function detectMismatch(item: SignalPulseItem): GateAgentMismatch {
  const highGate = item.score_band === "high_conviction" || item.score_band === "trade_candidate";
  const confidence = item.decision.confidence ?? 0;
  const recommendation = item.decision.recommendation;
  if (!highGate || confidence >= GATE_AGENT_MISMATCH_CONFIDENCE) {
    return null;
  }
  return {
    gateLabel: `策略门：${scoreBandLabel(item.score_band)} (score ${item.candidate_score ?? 0})`,
    agentLabel: `Agent：${recommendation ?? "-"} · 置信度 ${confidence.toFixed(2)}`,
    note: "策略门将该资产推到 top 区间，但 Agent 最终置信度偏低。请核对调研、决策和证据链接。",
  };
}

function classifyAuthor(event: SocialEventDetail, authorShare: number): EvidenceAuthorTag {
  if (event.author_watched) {
    return "watched";
  }
  if (
    event.author_followers != null &&
    event.author_followers < AUTHOR_SPAM_FOLLOWER_MAX &&
    authorShare >= AUTHOR_SPAM_SHARE_MIN
  ) {
    return "spam_suspect";
  }
  if (event.author_followers != null && event.author_followers >= AUTHOR_KOL_FOLLOWER_MIN) {
    return "kol_signal";
  }
  return "normal";
}

function toneForAuthorTag(tag: EvidenceAuthorTag): Tone {
  if (tag === "spam_suspect") {
    return "risk";
  }
  if (tag === "watched") {
    return "health";
  }
  if (tag === "kol_signal") {
    return "opportunity";
  }
  return "info";
}

function formatAuthorTag(tag: EvidenceAuthorTag): string {
  switch (tag) {
    case "watched":
      return "watched";
    case "spam_suspect":
      return "spam suspect";
    case "kol_signal":
      return "KOL";
    default:
      return "normal";
  }
}

function scoreBandTone(value: string | null | undefined): Tone {
  if (value === "high_conviction" || value === "trade_candidate") {
    return "opportunity";
  }
  if (value === "risk_rejected_high_info") {
    return "risk";
  }
  return "info";
}

function scoreBandLabel(value: string | null | undefined): string {
  switch (value) {
    case "high_conviction":
      return "高确信度";
    case "trade_candidate":
      return "可交易候选";
    case "token_watch":
      return "代币观察";
    case "risk_rejected_high_info":
      return "高信号但被风控驳回";
    default:
      return value ?? "-";
  }
}

function authorRunIndex(
  events: SocialEventDetail[],
  event: SocialEventDetail,
  index: number,
): number {
  let count = 0;
  for (let i = 0; i <= index; i += 1) {
    if (events[i].author_handle === event.author_handle) {
      count += 1;
    }
  }
  return count;
}

function emptyStages(): SignalPulseStages {
  return {
    investigator: null,
    decision_maker: null,
    research_only_gate: null,
    analyst: null,
    critic: null,
    judge: null,
  };
}

function formatConfidence(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "n/a" : value.toFixed(2);
}

function formatAction(action: string): string {
  switch (action) {
    case "tweet":
      return "tweet";
    case "quote":
      return "quote";
    case "repost":
      return "repost";
    case "reply":
      return "reply";
    default:
      return action;
  }
}

function shortenId(value: string): string {
  return value.length <= 24 ? value : `${value.slice(0, 14)}...${value.slice(-5)}`;
}

function msToHuman(value: number | null): string {
  if (!value) {
    return "n/a";
  }
  if (value < 60_000) {
    return `${Math.round(value / 1000)}s`;
  }
  if (value < 3_600_000) {
    return `${Math.round(value / 60_000)}m`;
  }
  return `${(value / 3_600_000).toFixed(1)}h`;
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function numOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
