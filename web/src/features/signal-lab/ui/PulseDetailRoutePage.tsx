import { getAuthToken } from "@lib/api/client";
import type { SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import { PanelSkeleton, RouteStatePanel } from "@shared/ui/RemoteState";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useSignalPulseCandidate, useSourceEvents } from "../api/useSignalPulseQueries";
import { parseSignalPulseVisibility } from "../state/signalLabRouteState";

import { PulseDetailView } from "./PulseDetail";

export function PulseDetailRoutePage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const [searchParams] = useSearchParams();
  const visibility = parseSignalPulseVisibility(searchParams.get("visibility"));
  const token = getAuthToken() ?? "";
  const pulse = useSignalPulseCandidate({ token, candidateId: candidateId ?? null, visibility });
  const item = pulse.data?.data ?? null;
  const sourceEvents = useSourceEvents({ token, ids: item?.source_event_ids ?? [] });

  if (pulse.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (pulse.isError || !item) {
    return (
      <RouteStatePanel title="Pulse 不存在或已被屏蔽">
        检查链接，或回到 Signal Pulse 列表选择其他候选。
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
  const backSearch = item.display_status?.startsWith("hidden_") ? "?visibility=hidden" : "";
  return (
    <>
      <Link to={`/signal-lab${backSearch}`}>返回列表</Link>
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
