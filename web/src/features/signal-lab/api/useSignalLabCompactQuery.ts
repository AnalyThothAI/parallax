import { getApi } from "@lib/api/client";
import type { SignalPulseData } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

const SIGNAL_LAB_COMPACT_WINDOW = "1h";
const SIGNAL_LAB_COMPACT_SCOPE = "all";

export function useSignalLabCompactQuery({ token }: { token: string }) {
  const overviewQuery = useQuery({
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

  const compactQuery = useQuery({
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

  const overviewData = overviewQuery.data?.data ?? compactQuery.data?.data;
  const pulseData = compactQuery.data?.data ?? overviewData;

  return useMemo(
    () => ({
      compactSignalPulseItems: pulseData?.items ?? [],
      overviewData,
      pulseData,
      signalPulseColdLoading: compactQuery.isPending && !pulseData,
      signalPulseFetching: compactQuery.isFetching,
      signalPulseTotal: signalPulseTotal(overviewData?.summary),
    }),
    [compactQuery.isFetching, compactQuery.isPending, overviewData, pulseData],
  );
}

function signalPulseTotal(summary?: SignalPulseData["summary"]): number {
  if (!summary) {
    return 0;
  }
  return (
    Number(summary.trade_candidate ?? 0) +
    Number(summary.token_watch ?? 0) +
    Number(summary.risk_rejected_high_info ?? 0)
  );
}
