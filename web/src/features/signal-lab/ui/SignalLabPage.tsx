import type { LivePayload, SignalPulseData } from "@lib/types";
import { Outlet } from "react-router-dom";

import { useSignalLabPage } from "../useSignalLabPage";

import { SignalLabWorkbench } from "./SignalLabWorkbench";

type SignalLabPageProps = {
  selectedAccountEventId?: string | null;
  overviewData?: SignalPulseData;
  onSelectAccountEvent?: (item: LivePayload) => void;
};

export function SignalLabPage({
  selectedAccountEventId = null,
  overviewData,
  onSelectAccountEvent,
}: SignalLabPageProps) {
  const signalLab = useSignalLabPage({ onSelectAccountEvent });

  return (
    <section
      className={`mobile-task-surface signal-lab-task-surface signal-lab-layout${signalLab.isPulseRoute ? " signal-lab-layout-with-detail" : ""}`}
      data-mobile-task-panel="lab"
    >
      <div className="signal-lab-list">
        <SignalLabWorkbench
          data={signalLab.signalPulseData}
          accountEvents={signalLab.signalLabAccountEvents}
          handleFilter={signalLab.routeState.handle}
          isAccountEventsLoading={signalLab.isAccountEventsLoading}
          isLoading={signalLab.isSignalPulseLoading}
          isFetchingNextPage={signalLab.isFetchingNextPage}
          hasNextPage={signalLab.hasNextPage}
          overviewData={overviewData}
          searchFilter={signalLab.routeState.q}
          selectedAccountEventId={selectedAccountEventId}
          selectedItemId={signalLab.selectedPulseItemId}
          statusFilter={signalLab.routeState.status}
          windowLabel={signalLab.routeState.window}
          onClearFilters={signalLab.clearFilters}
          onHandleChange={signalLab.setHandleFilter}
          onLoadMore={signalLab.loadMore}
          onSearchChange={signalLab.updateSearchFilter}
          onSelectAccountEvent={signalLab.selectAccountEvent}
          onSelect={signalLab.selectPulse}
          onStatusChange={signalLab.setStatusFilter}
        />
      </div>
      <aside className="signal-lab-inspector-pane">
        <Outlet />
      </aside>
    </section>
  );
}
