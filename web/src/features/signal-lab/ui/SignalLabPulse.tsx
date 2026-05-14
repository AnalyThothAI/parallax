import { compactNumber } from "@lib/format";
import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import { FlaskConical } from "lucide-react";

import { SignalPulseQueue } from "./SignalPulseQueue";

type SignalLabPulseProps = {
  data?: SignalPulseData;
  isLoading?: boolean;
  selectedItemId?: string | null;
  mobileTaskPanel?: "lab";
  onSelect: (item: SignalPulseItem) => void;
};

export function SignalLabPulse({
  data,
  isLoading,
  selectedItemId,
  mobileTaskPanel,
  onSelect,
}: SignalLabPulseProps) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const summary = data?.summary;
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Pulse</h2>
        </div>
        <div className="signal-attention-summary" aria-label="signal pulse summary">
          <SummaryPill label="候选" value={summary?.trade_candidate ?? 0} />
          <SummaryPill label="代币" value={summary?.token_watch ?? 0} />
          <SummaryPill label="拒绝" value={summary?.risk_rejected_high_info ?? 0} />
        </div>
      </header>
      <SignalPulseQueue
        compact
        isLoading={isLoading}
        items={items}
        selectedItemId={selectedItemId}
        onSelect={onSelect}
      />
    </section>
  );
}

function SummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <span>
      {label} <b>{compactNumber(value)}</b>
    </span>
  );
}
