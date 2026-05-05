import type { AttentionSeedItem, HarnessCreditItem, HarnessOutcomeItem, HarnessSnapshotItem, SocialEventItem } from "../api/types";
import { formatPercentShare } from "../lib/format";
import { CreditLedger } from "./CreditLedger";
import { HarnessTrace } from "./HarnessTrace";
import { OutcomeCard } from "./OutcomeCard";
import { SnapshotLedger } from "./SnapshotLedger";

export type HarnessDetailTab = "trace" | "snapshot" | "outcome" | "credit";

type HarnessDetailDrawerProps = {
  socialEvent?: SocialEventItem | null;
  seed?: AttentionSeedItem | null;
  snapshot?: HarnessSnapshotItem | null;
  outcome?: HarnessOutcomeItem | null;
  credits: HarnessCreditItem[];
  activeTab: HarnessDetailTab;
  onTabChange: (tab: HarnessDetailTab) => void;
};

const DETAIL_TABS: { tab: HarnessDetailTab; label: string }[] = [
  { tab: "trace", label: "Trace" },
  { tab: "snapshot", label: "Snapshot" },
  { tab: "outcome", label: "Outcome" },
  { tab: "credit", label: "Credit" }
];

export function HarnessDetailDrawer({ activeTab, credits, outcome, seed, snapshot, socialEvent, onTabChange }: HarnessDetailDrawerProps) {
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
      <nav className="tabs signal-detail-tabs" aria-label="signal detail tabs" role="tablist">
        {DETAIL_TABS.map(({ label, tab }) => (
          <button
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            key={tab}
            role="tab"
            type="button"
            onClick={() => onTabChange(tab)}
          >
            {label}
          </button>
        ))}
      </nav>
      <section className="drawer-section" role="tabpanel">
        {activeTab === "trace" ? <HarnessTrace credits={credits} outcome={outcome} seed={seed} snapshot={snapshot} socialEvent={socialEvent} /> : null}
        {activeTab === "snapshot" ? <SnapshotLedger snapshot={snapshot ?? null} /> : null}
        {activeTab === "outcome" ? <OutcomeCard outcome={outcome} status={snapshot?.outcome_status ?? "pending"} /> : null}
        {activeTab === "credit" ? <CreditLedger credits={credits} /> : null}
      </section>
    </aside>
  );
}
