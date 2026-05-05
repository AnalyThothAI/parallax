import type { HarnessOutcomeItem, HarnessSnapshotItem } from "../api/types";
import { formatPercentShare } from "../lib/format";
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
        <div className="empty-state">{status === "pending" ? "outcome pending · horizon not reached" : status}</div>
      </div>
    );
  }
  return (
    <div className="outcome-card ledger-box">
      <h3>Latest Outcome</h3>
      <Metric label="actual_return" value={formatPercentShare(outcome.actual_return)} />
      <Metric label="expected_return" value={formatPercentShare(outcome.expected_return)} />
      <Metric label="abnormal_return" tone={outcome.abnormal_return >= 0 ? "positive" : "negative"} value={formatPercentShare(outcome.abnormal_return)} />
      <Metric label="realized_vol" value={formatPercentShare(outcome.realized_vol)} />
      <Metric label="normalized_outcome" tone={outcome.normalized_outcome >= 0 ? "positive" : "negative"} value={outcome.normalized_outcome.toFixed(2)} />
      <Metric label="baseline" value={signalLabLabel(outcome.baseline_version)} />
    </div>
  );
}

function Metric({ label, tone, value }: { label: string; tone?: "positive" | "negative"; value: string }) {
  return (
    <div className="ledger-row">
      <span>{label}</span>
      <b className={tone}>{value}</b>
    </div>
  );
}
