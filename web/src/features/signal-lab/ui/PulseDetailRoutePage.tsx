import { getAuthToken } from "@lib/api/client";
import type { SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import { PanelSkeleton, RouteStatePanel } from "@shared/ui/RemoteState";
import { Link, useParams } from "react-router-dom";

import { useSignalPulseCandidate, useSourceEvents } from "../api/useSignalPulseQueries";

import { PulseDetailView } from "./PulseDetail";

export function PulseDetailRoutePage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = getAuthToken() ?? "";
  const pulse = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });
  const item = pulse.data?.data ?? null;
  const sourceEvents = useSourceEvents({ token, ids: item?.source_event_ids ?? [] });

  if (pulse.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (pulse.isError || !item) {
    return (
      <RouteStatePanel title="Pulse 不存在或已被屏蔽">
        检查链接，或回到 Signal Pulse 队列选择其他候选。
      </RouteStatePanel>
    );
  }

  return (
    <PulseDetailView
      actions={<PulseDetailActions item={item} />}
      density="full"
      item={item}
      sourceEvents={sourceEvents.data ?? []}
    />
  );
}

function PulseDetailActions({ item }: { item: SignalPulseItem }) {
  const subject = item.factor_snapshot.subject.symbol ?? item.symbol ?? item.subject_key;
  return (
    <>
      <Link to="/signal-lab">Back to queue</Link>
      <Link to={searchPath({ q: subject ? `$${subject.replace(/^\$+/, "")}` : item.subject_key })}>
        Search Intel
      </Link>
      {signalPulseVenueActions(item).map((action) => (
        <a href={action.url} key={`${action.label}:${action.url}`} rel="noreferrer" target="_blank">
          {action.label}
        </a>
      ))}
    </>
  );
}
