import type { LivePayload, SignalPulseData } from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { Outlet } from "react-router-dom";

import { useSignalLabPage } from "../useSignalLabPage";

import { SignalLabInspector } from "./SignalLabInspector";
import { SignalLabWorkbench } from "./SignalLabWorkbench";
import "./signalLab.css";

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
  const inlinePulseItem =
    signalLab.signalPulseData?.items.find(
      (item) => item.candidate_id === signalLab.selectedPulseItemId,
    ) ??
    signalLab.signalPulseData?.items[0] ??
    null;
  const shouldShowDetail = true;

  return (
    <section
      className={clsx(
        "mobile-task-surface",
        "signal-lab-task-surface",
        "signal-lab-layout",
        shouldShowDetail && "signal-lab-layout-with-detail",
      )}
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
        {signalLab.isPulseRoute ? (
          <Outlet />
        ) : inlinePulseItem ? (
          <SignalLabInspector item={inlinePulseItem} />
        ) : (
          <RemoteState.Empty title="No selected Signal Pulse case." />
        )}
      </aside>
    </section>
  );
}
