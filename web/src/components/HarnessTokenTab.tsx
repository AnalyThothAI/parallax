import type { AttentionSeedItem, HarnessCreditItem, HarnessOutcomeItem, HarnessSnapshotItem, TokenFlowItem } from "../api/types";
import { tokenLabel } from "../lib/format";
import { CreditLedger } from "./CreditLedger";
import { OutcomeCard } from "./OutcomeCard";
import { SnapshotLedger } from "./SnapshotLedger";

type HarnessTokenTabProps = {
  token: TokenFlowItem;
  seeds: AttentionSeedItem[];
  snapshots: HarnessSnapshotItem[];
  outcomes: HarnessOutcomeItem[];
  credits: HarnessCreditItem[];
  isLoading?: boolean;
  onSelectSnapshot: (snapshot: HarnessSnapshotItem) => void;
};

export function HarnessTokenTab({ token, seeds, snapshots, outcomes, credits, isLoading, onSelectSnapshot }: HarnessTokenTabProps) {
  const latestSnapshot = snapshots[0] ?? null;
  const latestOutcome = latestSnapshot ? outcomes.find((item) => item.snapshot_id === latestSnapshot.snapshot_id) : null;
  return (
    <div className="harness-token-tab">
      {isLoading ? <div className="empty-state">loading signal lab state</div> : null}
      <section className="ledger-box">
        <h3>Linked Seeds · {tokenLabel(token)}</h3>
        {seeds.length === 0 ? <div className="empty-state">当前 token 暂无 linked seed</div> : null}
        {seeds.map((seed) => (
          <article className="token-seed-row" key={seed.seed_id}>
            <strong>
              @{seed.author_handle ?? "watched"} · {seed.event_type}
            </strong>
            <span>{seed.subject}</span>
            <b>{seed.seed_status}</b>
          </article>
        ))}
      </section>
      <section className="ledger-box">
        <h3>Active Snapshots</h3>
        {snapshots.length === 0 ? <div className="empty-state">当前 token 暂无 active snapshot</div> : null}
        {snapshots.map((snapshot) => (
          <button className="snapshot-row" key={snapshot.snapshot_id} type="button" onClick={() => onSelectSnapshot(snapshot)}>
            <strong>
              {snapshot.asset} · {snapshot.horizon}
            </strong>
            <span>score {snapshot.combined_score.toFixed(2)}</span>
            <b>{snapshot.shadow_signal}</b>
          </button>
        ))}
      </section>
      <OutcomeCard outcome={latestOutcome} status={latestSnapshot?.outcome_status ?? "pending"} />
      <SnapshotLedger snapshot={latestSnapshot} />
      <CreditLedger credits={credits} />
    </div>
  );
}
