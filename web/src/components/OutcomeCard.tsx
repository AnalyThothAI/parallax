import type { HarnessOutcomeItem, HarnessSnapshotItem } from "../api/types";
import { formatPercentShare, formatRelativeTime } from "../lib/format";
import { signalLabLabel } from "../lib/signalLab";

type OutcomeCardProps = {
  outcome?: HarnessOutcomeItem | null;
  status: HarnessSnapshotItem["outcome_status"] | string;
};

export function OutcomeCard({ outcome, status }: OutcomeCardProps) {
  if (!outcome) {
    return (
      <div className="outcome-card ledger-box">
        <h3>Latest Outcome</h3>
        <Metric label="outcome_status" value={status} />
        <div className="empty-state">{outcomeEmptyState(status)}</div>
      </div>
    );
  }
  return (
    <div className="outcome-card ledger-box">
      <h3>Latest Outcome</h3>
      <Metric label="outcome_status" value={status} />
      <Metric label="settled_at_ms" value={formatRelativeTime(outcome.settled_at_ms)} />
      <Metric label="actual_return" value={formatPercentShare(outcome.actual_return)} />
      <Metric label="expected_return" value={formatPercentShare(outcome.expected_return)} />
      <Metric label="abnormal_return" tone={outcome.abnormal_return >= 0 ? "positive" : "negative"} value={formatPercentShare(outcome.abnormal_return)} />
      <Metric label="realized_vol" value={formatPercentShare(outcome.realized_vol)} />
      <Metric label="normalized_outcome" tone={outcome.normalized_outcome >= 0 ? "positive" : "negative"} value={outcome.normalized_outcome.toFixed(2)} />
      <Metric label="baseline_version" value={signalLabLabel(outcome.baseline_version)} />
    </div>
  );
}

function outcomeEmptyState(status: string): string {
  if (status === "missing_market") {
    return "Outcome blocked: no deterministic market entry for this asset.";
  }
  if (status === "insufficient_market_data") {
    return "Outcome blocked: horizon exit market data is unavailable.";
  }
  return status === "pending" ? "Outcome pending. Settlement waits for decision_time + horizon." : status;
}

function Metric({ label, tone, value }: { label: string; tone?: "positive" | "negative"; value: string }) {
  return (
    <div className="ledger-row">
      <span>{label}</span>
      <b className={tone}>{value}</b>
    </div>
  );
}
