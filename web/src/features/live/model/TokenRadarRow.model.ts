import { compactNumber, formatScore } from "@lib/format";
import type { TokenFlowItem } from "@lib/types";


export function compactLabel(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "-";
}

export function qualityLabel(item: TokenFlowItem): string {
  const reason = item.discussion_quality.reasons[0] ?? item.discussion_quality.risks[0] ?? "";
  const labels: Record<string, string> = {
    resolved_direct_evidence: "CA direct",
    informative_discussion: "informative",
    low_duplicate_share: "low dup",
    seed_linked: "seed+CA",
    catalyst: "catalyst",
    duplicate_text_cluster: "repeat",
    repeated_text_cluster: "repeat",
    low_information_posts: "meme only",
  };
  return labels[reason] ?? compactLabel(reason);
}

export function timingTitle(item: TokenFlowItem): string {
  const labels: Record<string, string> = {
    neutral: "neutral",
    market_pending: "market pending",
    market_unavailable: "market unavailable",
    chase_risk: "chase risk",
  };
  return labels[item.timing.status] ?? compactLabel(item.timing.status);
}

export function tokenDrawerSummary(item: TokenFlowItem) {
  return {
    heat: `${formatScore(item.social_heat.score)} / ${compactLabel(item.social_heat.status)}`,
    quality: `${formatScore(item.discussion_quality.score)} / ${drawerQualityLabel(item)}`,
    spread: `${compactNumber(item.propagation.independent_authors)} authors`,
    timing: timingTitle(item),
  };
}

function drawerQualityLabel(item: TokenFlowItem): string {
  const label = qualityLabel(item);
  return label === "CA direct" ? "direct" : label;
}
