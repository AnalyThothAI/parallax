import type { SignalLabChain, SignalLabInspectorTab } from "../api/types";
import { chainDisplayTitle, chainScore, chainSource } from "../lib/signalLabChains";
import { signalLabLabel } from "../lib/signalLab";
import { CreditLedger } from "./CreditLedger";
import { OutcomeCard } from "./OutcomeCard";
import { SignalTracePanel } from "./SignalTracePanel";
import { SnapshotLedger } from "./SnapshotLedger";

type SignalLabInspectorProps = {
  chain: SignalLabChain;
  activeTab: SignalLabInspectorTab;
  onTabChange: (tab: SignalLabInspectorTab) => void;
};

const DETAIL_TABS: { tab: SignalLabInspectorTab; label: string }[] = [
  { tab: "trace", label: "Trace" },
  { tab: "snapshot", label: "Snapshot" },
  { tab: "outcome", label: "Outcome" },
  { tab: "credit", label: "Credit" }
];

export function SignalLabInspector({ activeTab, chain, onTabChange }: SignalLabInspectorProps) {
  return (
    <aside className="detail-drawer drawer signal-lab-inspector">
      <header className="drawer-head">
        <div className="drawer-title">
          <div>
            <div className="eyebrow">selected signal chain</div>
            <h2>{chainDisplayTitle(chain)}</h2>
            <p>
              {chainSource(chain)} · {signalLabLabel(chain.social_event?.schema_version ?? chain.snapshot?.versions.schema_version)} · shadow only
            </p>
          </div>
          <div className="opportunity-score">{chainScore(chain)}</div>
        </div>
      </header>
      <nav className="tabs signal-detail-tabs" aria-label="signal chain detail tabs" role="tablist">
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
        {activeTab === "trace" ? <SignalTracePanel chain={chain} /> : null}
        {activeTab === "snapshot" ? <SnapshotLedger snapshot={chain.snapshot ?? null} /> : null}
        {activeTab === "outcome" ? <OutcomeCard outcome={chain.outcome ?? null} status={chain.snapshot?.outcome_status ?? chain.outcome_status ?? "pending"} /> : null}
        {activeTab === "credit" ? <CreditLedger credits={chain.credits} /> : null}
      </section>
    </aside>
  );
}
