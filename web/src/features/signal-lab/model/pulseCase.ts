import { compactNumber, formatUsdCompact, shortAddress } from "@lib/format";
import { requireTokenFactorSnapshot } from "@lib/tokenFactorSnapshot";
import type { SignalPulseItem, TokenFactorSnapshot } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import type {
  ObsidianSource,
  ObsidianStringEvidence,
  ObsidianStringField,
  ObsidianTone,
} from "@shared/ui/obsidianLanguage";

export type PulseCaseTone = ObsidianTone;

export type PulseCaseSource = ObsidianSource;

export type PulseCaseFact = ObsidianStringField;

export type PulseCaseEvidence = ObsidianStringEvidence;

export type PulseCaseAction = {
  href: string;
  kind: "search" | "venue";
  label: string;
};

export type PulseAgentMemo = {
  confidence: string;
  invalidations: string[];
  reasons: string[];
  recommendation: PulseCaseFact;
  risks: string[];
  summary: string;
  upgrades: string[];
};

export type PulseCaseView = {
  actions: PulseCaseAction[];
  agentMemo: PulseAgentMemo;
  candidateId: string;
  debugFacts: PulseCaseFact[];
  factLedger: PulseCaseFact[];
  gate: PulseCaseFact;
  sourceEvents: PulseCaseEvidence[];
  stage: PulseCaseFact;
  subject: {
    subtitle: string;
    title: string;
  };
};

export function buildPulseCaseView(item: SignalPulseItem): PulseCaseView {
  const snapshot = requireTokenFactorSnapshot(item.factor_snapshot);
  const title = subjectTitle(item, snapshot);
  const blockedReasons = [
    ...stringList(snapshot.gates.blocked_reasons),
    ...stringList(item.gate.blocked_reasons),
  ];
  const uniqueBlockedReasons = [...new Set(blockedReasons)];

  return {
    actions: [
      {
        href: searchPath({ q: searchQuery(item, snapshot) }),
        kind: "search",
        label: "Search Intel",
      },
      ...signalPulseVenueActions(item).map((action) => ({
        href: action.url,
        kind: "venue" as const,
        label: action.label,
      })),
    ],
    agentMemo: agentMemo(item),
    candidateId: item.candidate_id,
    debugFacts: debugFacts(item, snapshot),
    factLedger: factLedger(item, snapshot),
    gate: {
      detail:
        uniqueBlockedReasons.map(readableLabel).join(" · ") ||
        `score ${compactNumber(numberValue(item.gate.candidate_score) ?? item.candidate_score)}`,
      label: "Gate",
      source: "deterministic",
      tone: uniqueBlockedReasons.length ? "risk" : "health",
      value:
        stringValue(item.gate.score_band) ??
        item.score_band ??
        stringValue(item.gate.pulse_status) ??
        "-",
    },
    sourceEvents: sourceEvents(item),
    stage: {
      detail: [
        item.window,
        item.scope,
        readableLabel(item.narrative_type),
        readableLabel(item.social_phase),
      ]
        .filter((value): value is string => Boolean(value && value !== "-"))
        .join(" · "),
      label: "Stage",
      source: "deterministic",
      tone: stageTone(item.pulse_status),
      value: statusLabel(item.pulse_status),
    },
    subject: {
      subtitle: subjectSubtitle(item, snapshot),
      title,
    },
  };
}

function agentMemo(item: SignalPulseItem): PulseAgentMemo {
  const recommendation = item.agent_recommendation;
  return {
    confidence: percentValue(recommendation.confidence),
    invalidations: recommendation.invalidation_conditions.map(
      (condition) =>
        `${condition.factor_key} ${condition.operator} ${String(condition.value)}: ${condition.description_zh}`,
    ),
    reasons: recommendation.primary_reasons.map(
      (reason) => `${reason.factor_key}: ${reason.explanation_zh}`,
    ),
    recommendation: {
      detail: `schema ${recommendation.schema_version}`,
      label: "Agent verdict",
      source: "agent",
      tone: agentTone(recommendation.recommendation),
      value: recommendation.recommendation || "-",
    },
    risks: recommendation.residual_risks.map(
      (risk) => `${risk.factor_key}: ${risk.description_zh}`,
    ),
    summary: recommendation.summary_zh || "Agent memo unavailable.",
    upgrades: recommendation.upgrade_conditions.map(
      (condition) =>
        `${condition.factor_key} ${condition.operator} ${String(condition.value)}: ${condition.description_zh}`,
    ),
  };
}

function factLedger(item: SignalPulseItem, snapshot: TokenFactorSnapshot): PulseCaseFact[] {
  const market = snapshot.market.decision_latest ?? snapshot.market.event_anchor;
  const mentions =
    numberValue(item.fact_card.mentions_1h) ??
    numberValue(snapshot.families.social_heat.facts.mentions_1h);
  const authors =
    numberValue(item.fact_card.unique_authors) ??
    numberValue(snapshot.families.social_propagation.facts.independent_authors);
  return [
    marketFact("Market cap", item.fact_card.market_cap_usd, market?.market_cap_usd),
    marketFact("Liquidity", item.fact_card.liquidity_usd, market?.liquidity_usd),
    numberFact("Holders", item.fact_card.holders, market?.holders, "market"),
    marketFact("Volume 24h", item.fact_card.volume_24h_usd, market?.volume_24h_usd),
    {
      detail: watchedDetail(
        item.fact_card.watched_mentions,
        snapshot.families.social_heat.facts.watched_mentions,
      ),
      label: "Community",
      source: "social",
      tone: mentions || authors ? "health" : "neutral",
      value: `${compactNumber(mentions)} posts · ${compactNumber(authors)} authors`,
    },
    {
      detail: [
        `identity ${snapshot.data_health.identity}`,
        `market ${snapshot.data_health.market}`,
        `social ${snapshot.data_health.social}`,
        `alpha ${snapshot.data_health.alpha}`,
      ].join(" · "),
      label: "Data health",
      source: "deterministic",
      tone: Object.values(snapshot.data_health).every((value) => value === "ready")
        ? "health"
        : "info",
      value: snapshot.normalization.status ?? "unknown",
    },
    {
      detail: `cohort ${compactNumber(numberValue(snapshot.normalization.cohort_size))}`,
      label: "Alpha rank",
      source: "deterministic",
      tone: snapshot.normalization.alpha_rank ? "info" : "neutral",
      value: rankValue(snapshot.normalization.alpha_rank, snapshot.normalization.cohort_size),
    },
  ];
}

function marketFact(label: string, primary: unknown, fallback: unknown): PulseCaseFact {
  const value = numberValue(primary) ?? numberValue(fallback);
  return {
    detail: value === null ? "market value unavailable" : "market ledger",
    label,
    source: "market",
    tone: value === null ? "neutral" : "health",
    value: formatUsdCompact(value),
  };
}

function numberFact(
  label: string,
  primary: unknown,
  fallback: unknown,
  source: PulseCaseSource,
): PulseCaseFact {
  const value = numberValue(primary) ?? numberValue(fallback);
  return {
    detail: value === null ? "value unavailable" : "fact ledger",
    label,
    source,
    tone: value === null ? "neutral" : "health",
    value: compactNumber(value),
  };
}

function sourceEvents(item: SignalPulseItem): PulseCaseEvidence[] {
  const source = stringList(item.source_event_ids).map((id) => ({
    body: "Candidate source event",
    id,
    meta: "source_event_ids",
    title: id,
    tone: "info" as const,
  }));
  const evidence = stringList(item.evidence_event_ids).map((id) => ({
    body: "Agent evidence event",
    id,
    meta: "evidence_event_ids",
    title: id,
    tone: "health" as const,
  }));
  return [...source, ...evidence];
}

function debugFacts(item: SignalPulseItem, snapshot: TokenFactorSnapshot): PulseCaseFact[] {
  return [
    {
      detail: `schema ${snapshot.schema_version}`,
      label: "factor_snapshot",
      source: "deterministic",
      tone: "neutral",
      value: "available",
    },
    {
      detail: `keys ${Object.keys(item.gate).join(", ") || "-"}`,
      label: "gate",
      source: "deterministic",
      tone: "neutral",
      value: "available",
    },
    {
      detail: `${Array.isArray(item.playbooks) ? item.playbooks.length : 0} playbooks`,
      label: "playbooks",
      source: "deterministic",
      tone: "neutral",
      value: Array.isArray(item.playbooks) && item.playbooks.length ? "available" : "none",
    },
  ];
}

function subjectTitle(item: SignalPulseItem, snapshot: TokenFactorSnapshot): string {
  const symbol = snapshot.subject.symbol ?? item.symbol ?? item.subject_key;
  return symbol ? `$${symbol.replace(/^\$+/, "")}` : item.candidate_id;
}

function subjectSubtitle(item: SignalPulseItem, snapshot: TokenFactorSnapshot): string {
  if (snapshot.subject.chain || snapshot.subject.address) {
    return [snapshot.subject.chain, shortAddress(snapshot.subject.address)]
      .filter((value): value is string => Boolean(value && value !== "-"))
      .join(" · ");
  }
  return [
    snapshot.subject.target_type ?? item.target_type,
    snapshot.subject.target_id ?? item.target_id,
  ]
    .filter(Boolean)
    .join(" · ");
}

function searchQuery(item: SignalPulseItem, snapshot: TokenFactorSnapshot): string {
  const symbol = snapshot.subject.symbol ?? item.symbol;
  if (symbol?.trim()) {
    return `$${symbol.trim().replace(/^\$+/, "")}`;
  }
  return item.subject_key || item.target_id || item.candidate_id;
}

function watchedDetail(primary: unknown, fallback: unknown): string {
  return `watched ${compactNumber(numberValue(primary) ?? numberValue(fallback))}`;
}

function rankValue(rank: unknown, cohortSize: unknown): string {
  const parsedRank = numberValue(rank);
  if (parsedRank === null) {
    return "-";
  }
  const parsedCohortSize = numberValue(cohortSize);
  return parsedCohortSize === null ? `#${parsedRank}` : `#${parsedRank} / ${parsedCohortSize}`;
}

function percentValue(value: unknown): string {
  const number = numberValue(value);
  return number === null ? "-" : `${Math.round(number * 100)}%`;
}

function statusLabel(status: SignalPulseItem["pulse_status"]): string {
  if (status === "trade_candidate") return "trade candidate";
  if (status === "token_watch") return "token watch";
  if (status === "theme_watch") return "theme watch";
  return "risk rejected";
}

function stageTone(status: SignalPulseItem["pulse_status"]): PulseCaseTone {
  if (status === "trade_candidate") return "opportunity";
  if (status === "risk_rejected_high_info") return "risk";
  if (status === "token_watch") return "info";
  return "agent";
}

function agentTone(value: string): PulseCaseTone {
  if (value === "alert" || value === "trade_candidate") return "opportunity";
  if (value === "ignore") return "risk";
  if (value === "research") return "info";
  return "agent";
}

function readableLabel(value?: string | null): string {
  return value ? value.replaceAll("_", " ") : "-";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}
