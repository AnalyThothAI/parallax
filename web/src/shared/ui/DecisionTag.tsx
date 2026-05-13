import { formatDecision } from "@lib/format";
import type { Decision } from "@lib/types";
import clsx from "clsx";

export function DecisionTag({ decision }: { decision: Decision }) {
  return <span className={clsx("decision-tag", decision)}>{formatDecision(decision)}</span>;
}

export function RiskPill({ risk }: { risk: string }) {
  return <span className="risk-pill">{risk}</span>;
}
