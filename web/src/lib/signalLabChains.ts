import type { SignalLabChain, SignalLabStage, SignalLabStageSummary } from "../api/types";
import { compactNumber, formatRelativeTime, formatScore } from "./format";
import { signalLabLabel } from "./signalLab";

export const SIGNAL_LAB_STAGES: SignalLabStage[] = ["extracted", "seeded", "frozen", "settled", "credited"];

export const SIGNAL_LAB_STAGE_COPY: Record<SignalLabStage, { label: string; description: string }> = {
  extracted: { label: "Extracted", description: "LLM social-event objects." },
  seeded: { label: "Seeded", description: "Social events that became attention seeds." },
  frozen: { label: "Frozen", description: "Seeds with shadow snapshots." },
  settled: { label: "Settled", description: "Snapshots with outcome rows." },
  credited: { label: "Credited", description: "Settled snapshots with credit rows." }
};

export function chainDisplayTitle(chain: SignalLabChain): string {
  const asset = chainAssetLabel(chain);
  if (asset && chain.horizon) return `${asset} · ${chain.horizon}`;
  if (asset) return `${asset} · unresolved`;
  return chain.title || signalLabLabel(chain.chain_id);
}

export function chainSource(chain: SignalLabChain): string {
  return chain.source ? `@${chain.source.replace(/^@/, "")}` : "@unknown";
}

export function chainScore(chain: SignalLabChain): string {
  if (chain.snapshot?.shadow_signal === "NO_TRADE") {
    return "NO TRADE";
  }
  if (chain.score === null || chain.score === undefined) return "-";
  return `${formatScore(Math.abs(chain.score) <= 1 ? chain.score * 100 : chain.score)}%`;
}

export function chainRelativeTime(chain: SignalLabChain): string {
  return formatRelativeTime(chain.updated_at_ms || chain.received_at_ms);
}

export function chainStatusText(chain: SignalLabChain): string {
  const outcome = chain.outcome_status?.replaceAll("_", " ") || "no outcome";
  const rawCredit = chain.credit_status?.replaceAll("_", " ");
  const credit = !rawCredit || rawCredit === "none" ? "no credit" : rawCredit;
  return `${outcome} · ${credit}`;
}

function chainAssetLabel(chain: SignalLabChain): string | null {
  const seedSymbol = chain.seed?.top_linked_symbols?.[0];
  if (seedSymbol && chain.asset?.startsWith("token:")) {
    return seedSymbol;
  }
  return chain.asset ?? null;
}

export function totalChains(summary: SignalLabStageSummary | undefined, fallback: number): number {
  if (!summary) return fallback;
  return SIGNAL_LAB_STAGES.reduce((total, stage) => total + (summary[stage] ?? 0), 0);
}

export function stageCount(summary: SignalLabStageSummary | undefined, stage: SignalLabStage): string {
  return compactNumber(summary?.[stage] ?? 0);
}
