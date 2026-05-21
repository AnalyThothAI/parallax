import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import { FlaskConical } from "lucide-react";

import { SignalPulseQueue } from "./SignalPulseQueue";
import "./signalLab.css";

type SignalLabPulseProps = {
  data?: SignalPulseData;
  hiddenData?: SignalPulseData;
  hiddenIsLoading?: boolean;
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
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Pulse</h2>
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
