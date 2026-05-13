import { getAuthToken } from "@lib/api/client";
import { PanelSkeleton, RouteStatePanel } from "@shared/ui/RemoteState";
import { useParams } from "react-router-dom";

import { useSignalPulseCandidate } from "../api/useSignalPulseQueries";

import { SignalLabInspector } from "./SignalLabInspector";

export function PulseDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = getAuthToken() ?? "";
  const query = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });

  if (query.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (query.isError || !query.data?.data) {
    return (
      <RouteStatePanel title="Pulse 不存在或已被屏蔽">
        检查链接，或回到 Signal Pulse 队列选择其他候选。
      </RouteStatePanel>
    );
  }
  return <SignalLabInspector item={query.data.data} />;
}
