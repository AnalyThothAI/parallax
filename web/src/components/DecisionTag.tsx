import type { Decision } from "../api/types";
import { formatDecision } from "../lib/format";

export function DecisionTag({ decision }: { decision: Decision }) {
  return <span className={`decision-tag ${decision}`}>{formatDecision(decision)}</span>;
}

export function RiskPill({ risk }: { risk: string }) {
  return <span className="risk-pill">{risk}</span>;
}
