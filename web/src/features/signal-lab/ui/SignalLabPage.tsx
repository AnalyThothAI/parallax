import { getAuthToken } from "@lib/api/client";
import type { LivePayload, SignalPulseData, SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import clsx from "clsx";
import { Link } from "react-router-dom";

import { useSourceEvents } from "../api/useSignalPulseQueries";
import { useSignalLabPage } from "../useSignalLabPage";

import { PulseDetailView } from "./PulseDetail";
import { SignalLabWorkbench } from "./SignalLabWorkbench";
import "./SignalLabLayout.css";

type SignalLabPageProps = {
  selectedAccountEventId?: string | null;
  overviewData?: SignalPulseData;
  token?: string;
  onSelectAccountEvent?: (item: LivePayload) => void;
};

export function SignalLabPage({
  selectedAccountEventId = null,
  overviewData,
  token: tokenProp,
  onSelectAccountEvent,
}: SignalLabPageProps) {
  const signalLab = useSignalLabPage({ onSelectAccountEvent, token: tokenProp });
  const inlinePulseItem =
    signalLab.signalPulseData?.items.find(
      (item) => item.candidate_id === signalLab.selectedPulseItemId,
    ) ??
    signalLab.signalPulseData?.items[0] ??
    null;
  const shouldShowDetail = true;
  const token = tokenProp ?? getAuthToken() ?? "";
  const sourceEvents = useSourceEvents({ token, ids: inlinePulseItem?.source_event_ids ?? [] });

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
          visibilityFilter={signalLab.routeState.visibility}
          windowLabel={signalLab.routeState.window}
          onClearFilters={signalLab.clearFilters}
          onHandleChange={signalLab.setHandleFilter}
          onLoadMore={signalLab.loadMore}
          onSearchChange={signalLab.updateSearchFilter}
          onSelectAccountEvent={signalLab.selectAccountEvent}
          onSelect={signalLab.selectPulse}
          onStatusChange={signalLab.setStatusFilter}
          onVisibilityChange={signalLab.setVisibilityFilter}
        />
      </div>
      <aside className="signal-lab-inspector-pane">
        {inlinePulseItem ? (
          <PulseDetailView
            actions={<InlinePulseActions item={inlinePulseItem} />}
            density="compact"
            item={inlinePulseItem}
            sourceEvents={sourceEvents.data ?? []}
          />
        ) : (
          <PageState.Empty title="No selected Signal Pulse case." />
        )}
      </aside>
    </section>
  );
}

function InlinePulseActions({ item }: { item: SignalPulseItem }) {
  const subject = item.factor_snapshot.subject.symbol ?? item.symbol ?? item.subject_key;
  return (
    <>
      <Link to={`/signal-lab/pulse/${encodeURIComponent(item.candidate_id)}`}>打开完整视图 ↗</Link>
      <Link to={searchPath({ q: subject ? `$${subject.replace(/^\$+/, "")}` : item.subject_key })}>
        搜索情报
      </Link>
      {signalPulseVenueActions(item).map((action) => (
        <a href={action.url} key={`${action.label}:${action.url}`} rel="noreferrer" target="_blank">
          {action.label}
        </a>
      ))}
    </>
  );
}
