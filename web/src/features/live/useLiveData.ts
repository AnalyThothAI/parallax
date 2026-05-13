import { getApi, getBootstrap, setAuthToken } from "@lib/api/client";
import { countDecisions, sortTokenItems, tokenRadarItems } from "@lib/tokenRadar";
import type {
  RadarSortMode,
  RecentData,
  ScopeKey,
  SignalPulseData,
  StatusData,
  WindowKey,
} from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { targetRefFromTokenItem } from "../../domain/tokenTarget";

import { useTokenRadarQuery } from "./api/useTokenRadarQuery";

const SIGNAL_LAB_COMPACT_WINDOW = "1h";
const SIGNAL_LAB_COMPACT_SCOPE = "all";

type UseLiveDataArgs = {
  handles: string;
  radarSortMode: RadarSortMode;
  scope: ScopeKey;
  windowKey: WindowKey;
};

export function useLiveData({ handles, radarSortMode, scope, windowKey }: UseLiveDataArgs) {
  const [token, updateToken] = useState("");

  const bootstrapQuery = useQuery({
    queryKey: queryKeys.bootstrap(),
    queryFn: getBootstrap,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (bootstrapQuery.data?.data.ws_token) {
      const wsToken = bootstrapQuery.data.data.ws_token;
      setAuthToken(wsToken);
      updateToken(wsToken);
    }
  }, [bootstrapQuery.data?.data.ws_token]);

  const replayLimit = Math.min(25, bootstrapQuery.data?.data.replay_limit ?? 25);

  const statusQuery = useQuery({
    queryKey: queryKeys.status(),
    queryFn: () => getApi<StatusData>("/api/status", { token }),
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });

  const recentQuery = useQuery({
    queryKey: queryKeys.liveRecent(scope, handles),
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
    queryKey: queryKeys.signalLabOverview(SIGNAL_LAB_COMPACT_WINDOW, SIGNAL_LAB_COMPACT_SCOPE),
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
    queryKey: queryKeys.signalPulseCompact(SIGNAL_LAB_COMPACT_SCOPE, SIGNAL_LAB_COMPACT_WINDOW),
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

  const signalLabOverviewData =
    signalPulseOverviewQuery.data?.data ?? signalLabPulseQuery.data?.data;
  const signalLabPulseData = signalLabPulseQuery.data?.data ?? signalLabOverviewData;
  const compactSignalPulseItems = signalLabPulseData?.items ?? [];
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);

  return {
    assetFlowError: assetFlowQuery.error instanceof Error ? assetFlowQuery.error : null,
    bootstrapHandles: bootstrapQuery.data?.data.handles ?? [],
    compactSignalPulseItems,
    decisionCounts,
    handles,
    isAssetFlowLoading: assetFlowQuery.isPending,
    isRecentLoading: recentQuery.isPending,
    marketTargets,
    radarSortMode,
    recentReplayItems: recentQuery.data?.data.items ?? [],
    replayLimit,
    scope,
    signalPulseColdLoading: signalLabPulseQuery.isPending && !signalLabPulseData,
    signalPulseFetching: signalLabPulseQuery.isFetching,
    signalLabOverviewData,
    signalLabPulseData,
    signalLabPulseTotal: signalPulseTotal(signalLabOverviewData?.summary),
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
