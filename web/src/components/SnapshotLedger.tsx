import type { HarnessSnapshotItem } from "../api/types";
import { formatRelativeTime, formatScore } from "../lib/format";

type SnapshotLedgerProps = {
  snapshot: HarnessSnapshotItem | null;
};

export function SnapshotLedger({ snapshot }: SnapshotLedgerProps) {
  if (!snapshot) {
    return <div className="empty-state">snapshot_not_selected</div>;
  }
  return (
    <div className="snapshot-ledger ledger-box">
      <h3>Snapshot Ledger</h3>
      <LedgerRow label="snapshot_id" value={snapshot.snapshot_id} />
      <LedgerRow label="asset" value={snapshot.asset} />
      <LedgerRow label="horizon" value={snapshot.horizon} />
      <LedgerRow label="combined_score" value={formatScore(snapshot.combined_score * 100)} />
      <LedgerRow label="shadow_signal" value={snapshot.shadow_signal} />
      <LedgerRow label="policy_signal" value={snapshot.policy_signal} />
      <LedgerRow label="decision_time" value={formatRelativeTime(snapshot.decision_time_ms)} />
      <LedgerRow label="outcome" value={snapshot.outcome_status} />
      <LedgerRow label="credit" value={snapshot.credit_status} />
      <LedgerRow label="config" value={snapshot.versions.config_version} />
      <LedgerRow label="prompt" value={snapshot.versions.prompt_version} />
      <LedgerRow label="scoring" value={snapshot.versions.scoring_version} />
    </div>
  );
}

function LedgerRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="ledger-row">
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
