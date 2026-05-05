import type { HarnessSnapshotItem } from "../api/types";
import { formatRelativeTime, formatScore } from "../lib/format";
import { signalLabLabel } from "../lib/signalLab";

type SnapshotLedgerProps = {
  snapshot: HarnessSnapshotItem | null;
};

export function SnapshotLedger({ snapshot }: SnapshotLedgerProps) {
  if (!snapshot) {
    return <div className="empty-state">No snapshot for this chain and horizon.</div>;
  }
  return (
    <div className="snapshot-ledger ledger-box">
      <h3>Snapshot Ledger</h3>
      <LedgerRow label="snapshot_id" value={signalLabLabel(snapshot.snapshot_id)} />
      <LedgerRow label="source_event" value={signalLabLabel(snapshot.source_event_id)} />
      <LedgerRow label="seed" value={signalLabLabel(snapshot.seed_id)} />
      <LedgerRow label="asset" value={snapshot.asset} />
      <LedgerRow label="horizon" value={snapshot.horizon} />
      <LedgerRow label="combined_score" value={formatScore(snapshot.combined_score * 100)} />
      <LedgerRow label="shadow_signal" value={snapshot.shadow_signal} />
      <LedgerRow label="policy_signal" value={snapshot.policy_signal} />
      <LedgerRow label="decision_time" value={formatRelativeTime(snapshot.decision_time_ms)} />
      <LedgerRow label="outcome" value={snapshot.outcome_status} />
      <LedgerRow label="credit" value={snapshot.credit_status} />
      <LedgerRow label="config_version" value={signalLabLabel(snapshot.versions.config_version)} />
      <LedgerRow label="prompt_version" value={signalLabLabel(snapshot.versions.prompt_version)} />
      <LedgerRow label="schema_version" value={signalLabLabel(snapshot.versions.schema_version)} />
      <LedgerRow label="scoring_version" value={signalLabLabel(snapshot.versions.scoring_version)} />
      <LedgerRow label="weight_version" value={signalLabLabel(snapshot.versions.weight_version)} />
      <LedgerRow label="policy_version" value={signalLabLabel(snapshot.versions.policy_version)} />
      <LedgerRow label="risk_version" value={signalLabLabel(snapshot.versions.risk_version)} />
      <LedgerRow label="baseline_version" value={signalLabLabel(snapshot.versions.baseline_version)} />
      <LedgerRow label="risks" value={snapshot.risks.join(", ") || "-"} />
      <section className="ledger-subsection">
        <h4>Event Clusters</h4>
        {snapshot.event_clusters.length ? (
          snapshot.event_clusters.map((cluster) => (
            <article className="ledger-mini-row" key={cluster.cluster_id}>
              <b>{signalLabLabel(cluster.cluster_id)}</b>
              <span>
                {cluster.event_type} · {signalLabLabel(cluster.source)} · {cluster.event_score.toFixed(2)}
              </span>
            </article>
          ))
        ) : (
          <div className="empty-state">No event clusters.</div>
        )}
      </section>
      <section className="ledger-subsection">
        <h4>Market State</h4>
        {Object.entries(snapshot.market_state).length ? (
          Object.entries(snapshot.market_state).map(([key, value]) => <LedgerRow key={key} label={key} value={formatLedgerValue(value)} />)
        ) : (
          <div className="empty-state">No market state.</div>
        )}
      </section>
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

function formatLedgerValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}
