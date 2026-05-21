import { SignalLabPulse } from "@features/signal-lab";
import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import type { ReactNode } from "react";
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
  hiddenSignalLabPulseData: SignalPulseData | null;
  signalPulseLoading: boolean;
  hiddenSignalPulseLoading: boolean;
  selectedPulseItemId: string | null;
  children?: ReactNode;
  onSelectPulse: (item: SignalPulseItem) => void;
};

/**
 * LivePage frames the live cockpit: it renders the routed top region above a persistent
 * bottom-deck (tape + signal-lab compact pulse). Token Radar rows open the item route; compact
 * pulse rows open the Signal Pulse detail route.
 */
export function LivePage({
  liveSignalTapeItems,
  isRecentLoading,
  socketStatus,
  selectedTapeEventId,
  onTapeSelect,
  signalLabPulseData,
  hiddenSignalLabPulseData,
  signalPulseLoading,
  hiddenSignalPulseLoading,
  selectedPulseItemId,
  children,
  onSelectPulse,
}: LivePageProps) {
  return (
    <div data-testid="live-page" className="live-page">
      {children ?? <Outlet />}

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
          hiddenData={hiddenSignalLabPulseData ?? undefined}
          hiddenIsLoading={hiddenSignalPulseLoading}
          isLoading={signalPulseLoading}
          mobileTaskPanel="lab"
          selectedItemId={selectedPulseItemId}
          onSelect={onSelectPulse}
        />
      </div>
    </div>
  );
}
