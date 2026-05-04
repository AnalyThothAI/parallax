import type { Decision } from "../api/types";
import { formatDecision } from "../lib/format";

export function DecisionTag({ decision, manual }: { decision: Decision; manual?: boolean }) {
  return (
    <span className={`decision-tag ${decision} ${manual ? "manual" : ""}`}>
      {formatDecision(decision)}
      {manual ? " · 手动" : ""}
    </span>
  );
}

export function RiskPill({ risk }: { risk: string }) {
  return <span className="risk-pill">{risk}</span>;
}
