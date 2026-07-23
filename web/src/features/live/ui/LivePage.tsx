import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";

import type { LiveSignalTapeItem } from "../liveTapeModel";
import type { LiveMobileTask } from "../model/liveMobileTask";

import { LiveSignalTape } from "./LiveSignalTape";
import { LiveTaskNav } from "./LiveTaskNav";
import "./live.css";

type LivePageProps = {
  liveSignalTapeItems: LiveSignalTapeItem[];
  isRecentLoading: boolean;
  socketStatus: string;
  selectedTapeEventId: string | null;
  onTapeSelect: (item: LiveSignalTapeItem) => void;
  mobileTask: LiveMobileTask;
  children?: ReactNode;
  onMobileTaskChange: (task: LiveMobileTask) => void;
};

/**
 * LivePage frames the live cockpit: Token Radar owns the routed top region and the replay/live
 * event Tape owns the lower region. Mobile users switch between those two route-local tasks.
 */
export function LivePage({
  liveSignalTapeItems,
  isRecentLoading,
  socketStatus,
  selectedTapeEventId,
  onTapeSelect,
  mobileTask,
  children,
  onMobileTaskChange,
}: LivePageProps) {
  return (
    <div
      className={`live-page mobile-task-${mobileTask}`}
      data-page-archetype="scan"
      data-testid="live-page"
    >
      {children ?? <Outlet />}

      <LiveSignalTape
        isLoading={isRecentLoading}
        items={liveSignalTapeItems}
        mobileTaskPanel="tape"
        selectedEventId={selectedTapeEventId}
        socketStatus={socketStatus}
        onSelect={onTapeSelect}
      />

      <LiveTaskNav activeTask={mobileTask} onTaskChange={onMobileTaskChange} />
    </div>
  );
}
