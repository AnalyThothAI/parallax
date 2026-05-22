import { formatDecision } from "@lib/format";
import type { Decision } from "@lib/types";
import clsx from "clsx";

import "./DecisionTag.css";

const DECISION_TONES: Record<Decision, "opportunity" | "info" | "risk" | "neutral"> = {
  discard: "risk",
  driver: "opportunity",
  investigate: "info",
  watch: "neutral",
};

export function DecisionTag({ decision }: { decision: Decision }) {
  return (
    <span className={clsx("decision-tag", decision)} data-tone={DECISION_TONES[decision]}>
      {formatDecision(decision)}
    </span>
  );
}

export function RiskPill({ risk }: { risk: string }) {
  return (
    <span className="risk-pill" data-tone="risk">
      {risk}
    </span>
  );
}
