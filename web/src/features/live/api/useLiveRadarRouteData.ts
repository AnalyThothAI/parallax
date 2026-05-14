import { countDecisions, sortTokenItems, tokenRadarItems } from "@lib/tokenRadar";
import type { ScopeKey, WindowKey } from "@lib/types";
import { useMemo } from "react";

import { targetRefFromTokenItem } from "../../../domain/tokenTarget";

import { useTokenRadarQuery } from "./useTokenRadarQuery";

export function useLiveRadarRouteData({
  scope,
  token,
  window,
}: {
  scope: ScopeKey;
  token: string;
  window: WindowKey;
}) {
  const assetFlowQuery = useTokenRadarQuery({ token, window, scope, limit: 48 });
  const rawTokenItems = useMemo(
    () => tokenRadarItems(assetFlowQuery.data?.data, window, scope),
    [assetFlowQuery.data?.data, scope, window],
  );
  const tokenItems = useMemo(() => sortTokenItems(rawTokenItems), [rawTokenItems]);
  const marketTargets = useMemo(
    () =>
      rawTokenItems.flatMap((item) => {
        const target = targetRefFromTokenItem(item);
        return target ? [target] : [];
      }),
    [rawTokenItems],
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);

  return {
    assetFlowError: assetFlowQuery.error instanceof Error ? assetFlowQuery.error : null,
    decisionCounts,
    isAssetFlowLoading: assetFlowQuery.isPending,
    marketTargets,
    tokenItems,
  };
}
