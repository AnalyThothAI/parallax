import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";

import { getApi, getBootstrap } from "../../api/client";
import type {
  LivePayload,
  LiveMarketUpdatePayload,
  RecentData,
  SignalPulseData,
  StatusData,
} from "../../api/types";
import { useIntelSocket } from "../../api/useIntelSocket";
import { useTokenRadarQuery } from "../../api/useTokenRadarQuery";
import { targetRefFromTokenItem } from "../../domain/tokenTarget";
import { countDecisions, sortTokenItems, tokenRadarItems } from "../../lib/tokenRadar";
import { useTraderStore } from "../../store/useTraderStore";

import { patchTokenRadarLiveMarketUpdate } from "./liveMarketUpdatePatch";
import { buildLiveSignalTapeItems } from "./liveTapeModel";

const SIGNAL_LAB_COMPACT_WINDOW = "1h";
const SIGNAL_LAB_COMPACT_SCOPE = "all";

export function useLiveData() {
  const queryClient = useQueryClient();
  const windowKey = useTraderStore((state) => state.window);
  const scope = useTraderStore((state) => state.scope);
  const handles = useTraderStore((state) => state.handles);
  const token = useTraderStore((state) => state.token);
  const radarSortMode = useTraderStore((state) => state.radarSortMode);
  const setToken = useTraderStore((state) => state.setToken);

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap"],
    queryFn: getBootstrap,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (bootstrapQuery.data?.data.ws_token) {
      setToken(bootstrapQuery.data.data.ws_token);
    }
  }, [bootstrapQuery.data?.data.ws_token, setToken]);

  const replayLimit = Math.min(25, bootstrapQuery.data?.data.replay_limit ?? 25);

  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: () => getApi<StatusData>("/api/status", { token }),
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });

  const recentQuery = useQuery({
    queryKey: ["recent", scope, handles],
    queryFn: () =>
      getApi<RecentData>("/api/recent", {
        token,
        params: { limit: 80, scope, handles },
      }),
    enabled: Boolean(token),
    refetchInterval: 15_000,
  });

  const assetFlowQuery = useTokenRadarQuery({ token, window: windowKey, scope, limit: 48 });

  const signalPulseOverviewQuery = useQuery({
    queryKey: ["signal-lab-overview", SIGNAL_LAB_COMPACT_WINDOW, SIGNAL_LAB_COMPACT_SCOPE],
    queryFn: () =>
      getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: SIGNAL_LAB_COMPACT_WINDOW,
          scope: SIGNAL_LAB_COMPACT_SCOPE,
          limit: 1,
        },
      }),
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });

  const signalLabPulseQuery = useQuery({
    queryKey: ["signal-lab-pulse-compact", SIGNAL_LAB_COMPACT_SCOPE, SIGNAL_LAB_COMPACT_WINDOW],
    queryFn: () =>
      getApi<SignalPulseData>("/api/signal-lab/pulse", {
        token,
        params: {
          window: SIGNAL_LAB_COMPACT_WINDOW,
          scope: SIGNAL_LAB_COMPACT_SCOPE,
          limit: 80,
          sort: "recent",
        },
      }),
    enabled: Boolean(token),
    refetchInterval: 20_000,
  });

  const rawTokenItems = useMemo(
    () => tokenRadarItems(assetFlowQuery.data?.data, windowKey, scope),
    [assetFlowQuery.data?.data, scope, windowKey],
  );
  const tokenItems = useMemo(
    () => sortTokenItems(rawTokenItems, radarSortMode),
    [rawTokenItems, radarSortMode],
  );
  const marketTargets = useMemo(
    () =>
      rawTokenItems.flatMap((item) => {
        const target = targetRefFromTokenItem(item);
        return target ? [target] : [];
      }),
    [rawTokenItems],
  );

  const handleLiveMarketUpdate = useCallback(
    (payload: LiveMarketUpdatePayload) => patchTokenRadarLiveMarketUpdate(queryClient, payload),
    [queryClient],
  );

  const socket = useIntelSocket({
    token,
    handles,
    replay: replayLimit,
    notifications: true,
    marketTargets,
    onLiveMarketUpdate: handleLiveMarketUpdate,
  });
  const liveItems = useMemo(() => {
    const replayItems = recentQuery.data?.data.items ?? [];
    const byId = new Map<string, LivePayload>();
    for (const item of [...replayItems, ...socket.events]) {
      byId.set(item.event.event_id, item);
    }
    return [...byId.values()].sort(
      (a, b) => Number(b.event.received_at_ms ?? 0) - Number(a.event.received_at_ms ?? 0),
    );
  }, [recentQuery.data?.data.items, socket.events]);

  const signalLabOverviewData =
    signalPulseOverviewQuery.data?.data ?? signalLabPulseQuery.data?.data;
  const signalLabPulseData = signalLabPulseQuery.data?.data ?? signalLabOverviewData;
  const compactSignalPulseItems = signalLabPulseData?.items ?? [];
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems],
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);

  return {
    assetFlowError: assetFlowQuery.error instanceof Error ? assetFlowQuery.error : null,
    bootstrapHandles: bootstrapQuery.data?.data.handles ?? [],
    compactSignalPulseItems,
    decisionCounts,
    handles,
    isAssetFlowLoading: assetFlowQuery.isPending,
    isRecentLoading: recentQuery.isPending,
    isSignalLabPulseColdLoading: signalLabPulseQuery.isPending && !signalLabPulseData,
    isSignalLabPulseFetching: signalLabPulseQuery.isFetching,
    liveItems,
    liveSignalTapeItems,
    radarSortMode,
    scope,
    signalLabOverviewData,
    signalLabPulseData,
    signalLabPulseTotal: signalPulseTotal(signalLabOverviewData?.summary),
    socket,
    status: statusQuery.data?.data ?? null,
    statusError: statusQuery.isError,
    statusHandles: statusQuery.data?.data.handles ?? [],
    statusLoading: Boolean(token) && statusQuery.isPending,
    token,
    tokenItems,
    windowKey,
  };
}

function signalPulseTotal(summary?: SignalPulseData["summary"]): number {
  if (!summary) {
    return 0;
  }
  return (
    Number(summary.trade_candidate ?? 0) +
    Number(summary.token_watch ?? 0) +
    Number(summary.theme_watch ?? 0) +
    Number(summary.risk_rejected_high_info ?? 0)
  );
}
