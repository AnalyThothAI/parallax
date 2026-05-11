import { useParams } from "react-router-dom";

import { useSignalPulseCandidate } from "../api/useSignalPulseQueries";
import { useTraderStore } from "../store/useTraderStore";
<<<<<<< HEAD

=======
import { PanelSkeleton, RouteStatePanel } from "../shared/ui/RemoteState";
>>>>>>> origin/main
import { SignalLabInspector } from "./SignalLabInspector";

export function PulseDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = useTraderStore((state) => state.token);
  const query = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });

  if (query.isLoading) {
    return <PanelSkeleton label="loading pulse detail" />;
  }
  if (query.isError || !query.data?.data) {
    return <RouteStatePanel title="Pulse 不存在或已被屏蔽">检查链接，或回到 Signal Lab 列表选择其他候选。</RouteStatePanel>;
  }
  return <SignalLabInspector item={query.data.data} />;
}
