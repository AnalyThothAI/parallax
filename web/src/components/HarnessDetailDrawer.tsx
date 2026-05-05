import type { AttentionSeedItem, HarnessCreditItem, HarnessOutcomeItem, HarnessSnapshotItem, SocialEventItem } from "../api/types";
import { formatPercentShare } from "../lib/format";
import { CreditLedger } from "./CreditLedger";
import { HarnessTrace } from "./HarnessTrace";
import { OutcomeCard } from "./OutcomeCard";
import { SnapshotLedger } from "./SnapshotLedger";

type HarnessDetailDrawerProps = {
  socialEvent?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
};

export function HarnessDetailDrawer({ socialEvent, seed, snapshot, outcome, credits }: HarnessDetailDrawerProps) {
  const title = snapshot ? `${snapshot.asset} · ${snapshot.horizon}` : socialEvent ? `@${socialEvent.author_handle ?? "watched"} · ${socialEvent.event_type}` : seed ? `@${seed.author_handle ?? "watched"} · ${seed.event_type}` : "Signal Lab";
  const score = snapshot?.combined_score ?? socialEvent?.confidence ?? null;
  return (
    <aside className="detail-drawer drawer">
      <header className="drawer-head">
        <div className="drawer-title">
          <div>
            <div className="eyebrow">selected signal object</div>
            <h2>{title}</h2>
            <p>social-event-v1 · shadow only</p>
          </div>
          <div className="opportunity-score">{score === null ? "-" : formatPercentShare(score)}</div>
        </div>
      </header>
      <nav className="tabs" aria-label="signal detail tabs">
        <button className="active" type="button">
          Trace
        </button>
        <button type="button">Snapshot</button>
        <button type="button">Outcome</button>
        <button type="button">Credit</button>
      </nav>
      <section className="drawer-section">
        <HarnessTrace credits={credits} outcome={outcome} seed={seed} snapshot={snapshot} socialEvent={socialEvent} />
        <SnapshotLedger snapshot={snapshot ?? null} />
        <OutcomeCard outcome={outcome} status={snapshot?.outcome_status ?? "pending"} />
        <CreditLedger credits={credits} />
      </section>
    </aside>
  );
}
