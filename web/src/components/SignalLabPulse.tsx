import { FlaskConical } from "lucide-react";
import type { SignalLabChain, SignalLabChainsData } from "../api/types";
import { SignalChainList } from "./SignalChainList";

type SignalLabPulseProps = {
  data?: SignalLabChainsData;
  isLoading?: boolean;
  selectedChainId?: string | null;
  mobileTaskPanel?: "lab";
  onOpenLab: () => void;
  onSelect: (chain: SignalLabChain) => void;
};

export function SignalLabPulse({ data, isLoading, selectedChainId, mobileTaskPanel, onOpenLab, onSelect }: SignalLabPulseProps) {
  const pulseItems = [...(data?.items ?? [])].sort((a, b) => signalPulseRank(b) - signalPulseRank(a) || b.updated_at_ms - a.updated_at_ms).slice(0, 5);
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Lab Pulse</h2>
        </div>
        <button className="text-action" type="button" onClick={onOpenLab}>
          Open Lab
        </button>
      </header>
      <SignalChainList compact isLoading={isLoading} items={pulseItems} selectedChainId={selectedChainId} onSelect={onSelect} />
    </section>
  );
}

function signalPulseRank(chain: SignalLabChain): number {
  if (chain.stage === "credited") return 5;
  if (chain.stage === "settled") return 4;
  if (chain.stage === "frozen") return 3;
  if (chain.stage === "seeded") return 2;
  return 1;
}
