import { SignalLabPulse } from "@features/signal-lab";
import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import { Outlet } from "react-router-dom";

import type { LiveSignalTapeItem } from "../liveTapeModel";

import { LiveSignalTape } from "./LiveSignalTape";
import "./live.css";

type LivePageProps = {
  liveSignalTapeItems: LiveSignalTapeItem[];
  isRecentLoading: boolean;
  socketStatus: string;
  selectedTapeEventId: string | null;
  onTapeSelect: (item: LiveSignalTapeItem) => void;
  signalLabPulseData: SignalPulseData | null;
  signalPulseLoading: boolean;
  selectedPulseItemId: string | null;
  onOpenLab: () => void;
  onSelectPulse: (item: SignalPulseItem) => void;
};

/**
 * LivePage frames the live cockpit: it renders the routed top region above a persistent
 * bottom-deck (tape + signal-lab compact pulse). Token Radar rows open the item route; compact
 * pulse rows open the Signal Pulse route.
 */
export function LivePage({
  liveSignalTapeItems,
  isRecentLoading,
  socketStatus,
  selectedTapeEventId,
  onTapeSelect,
  signalLabPulseData,
  signalPulseLoading,
  selectedPulseItemId,
  onOpenLab,
  onSelectPulse,
}: LivePageProps) {
  return (
    <div data-testid="live-page" className="live-page">
      <Outlet />

      <div className="bottom-deck">
        <LiveSignalTape
          isLoading={isRecentLoading}
          items={liveSignalTapeItems}
          mobileTaskPanel="tape"
          selectedEventId={selectedTapeEventId}
          socketStatus={socketStatus}
          onSelect={onTapeSelect}
        />

        <SignalLabPulse
          data={signalLabPulseData ?? undefined}
          isLoading={signalPulseLoading}
          mobileTaskPanel="lab"
          selectedItemId={selectedPulseItemId}
          onOpenLab={onOpenLab}
          onSelect={onSelectPulse}
        />
      </div>
    </div>
  );
}
