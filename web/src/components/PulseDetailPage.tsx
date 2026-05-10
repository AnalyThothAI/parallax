import { useParams } from "react-router-dom";

import { useSignalPulseCandidate } from "../api/useSignalPulseQueries";
import { useTraderStore } from "../store/useTraderStore";

import { SignalLabInspector } from "./SignalLabInspector";

export function PulseDetailPage() {
  const { candidateId } = useParams<{ candidateId: string }>();
  const token = useTraderStore((state) => state.token);
  const query = useSignalPulseCandidate({ token, candidateId: candidateId ?? null });

  if (query.isLoading) {
    return <div className="empty-state">加载中…</div>;
  }
  if (query.isError || !query.data?.data) {
    return <div className="empty-state">Pulse 不存在或已被屏蔽</div>;
  }
  return <SignalLabInspector item={query.data.data} />;
}
