import { compactNumber } from "@lib/format";
import type { SignalPulseData, SignalPulseItem, SignalPulseVisibilityFilter } from "@lib/types";
import * as Tabs from "@radix-ui/react-tabs";
import { FlaskConical } from "lucide-react";
import { useState } from "react";

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
  hiddenData,
  hiddenIsLoading,
  isLoading,
  selectedItemId,
  mobileTaskPanel,
  onSelect,
}: SignalLabPulseProps) {
  const [visibility, setVisibility] = useState<SignalPulseVisibilityFilter>("public");
  const activeData = visibility === "hidden" ? hiddenData : data;
  const activeLoading = visibility === "hidden" ? hiddenIsLoading : isLoading;
  const items = Array.isArray(activeData?.items) ? activeData.items : [];
  const publicCount = publicPulseCount(data);
  const hiddenCount = hiddenPulseCount(data, hiddenData);
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Pulse</h2>
        </div>
        <CompactVisibilityTabs
          hiddenCount={hiddenCount}
          publicCount={publicCount}
          value={visibility}
          onChange={setVisibility}
        />
      </header>
      <SignalPulseQueue
        compact
        isLoading={activeLoading}
        items={items}
        selectedItemId={selectedItemId}
        onSelect={onSelect}
      />
    </section>
  );
}

function CompactVisibilityTabs({
  hiddenCount,
  publicCount,
  value,
  onChange,
}: {
  hiddenCount: number;
  publicCount: number;
  value: SignalPulseVisibilityFilter;
  onChange: (visibility: SignalPulseVisibilityFilter) => void;
}) {
  return (
    <Tabs.Root
      className="signal-compact-visibility-tabs"
      value={value}
      activationMode="manual"
      onValueChange={(next) => onChange(next as SignalPulseVisibilityFilter)}
    >
      <Tabs.List aria-label="Signal Pulse visibility" className="signal-compact-tab-list">
        <Tabs.Trigger value="public">
          公开 <b>{compactNumber(publicCount)}</b>
        </Tabs.Trigger>
        <Tabs.Trigger value="hidden">
          隐藏 <b>{compactNumber(hiddenCount)}</b>
        </Tabs.Trigger>
      </Tabs.List>
    </Tabs.Root>
  );
}

function publicPulseCount(data?: SignalPulseData): number {
  const healthCount = data?.health.public_candidate_count;
  if (typeof healthCount === "number") {
    return healthCount;
  }
  return signalPulseSummaryCount(data?.summary);
}

function hiddenPulseCount(publicData?: SignalPulseData, hiddenData?: SignalPulseData): number {
  const publicHealthCount = publicData?.health.hidden_candidate_count;
  if (typeof publicHealthCount === "number") {
    return publicHealthCount;
  }
  const hiddenHealthCount = hiddenData?.health.hidden_candidate_count;
  if (typeof hiddenHealthCount === "number") {
    return hiddenHealthCount;
  }
  return hiddenData?.returned_count ?? hiddenData?.items.length ?? 0;
}

function signalPulseSummaryCount(summary?: SignalPulseData["summary"]): number {
  return (
    Number(summary?.trade_candidate ?? 0) +
    Number(summary?.token_watch ?? 0) +
    Number(summary?.risk_rejected_high_info ?? 0)
  );
}
