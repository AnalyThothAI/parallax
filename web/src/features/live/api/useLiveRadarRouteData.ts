import { countDecisions, sortTokenItems, tokenRadarItems } from "@lib/tokenRadar";
import type { AssetFlowData, ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { useEffect, useMemo, useRef } from "react";

import { targetRefFromTokenItem } from "../../../domain/tokenTarget";

import { useTokenRadarQuery } from "./useTokenRadarQuery";

type RadarFrame = {
  rawTokenItems: TokenFlowItem[];
  tokenItems: TokenFlowItem[];
};

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
  const lastReadyFrames = useRef(new Map<string, RadarFrame>());
  const cacheKey = `${window}:${scope}`;
  const projectionStatus = assetFlowQuery.data?.data?.projection?.status ?? null;
  const projectionPending = projectionStatus === "pending";
  const parsed = useMemo(
    () => parseTokenRadarItems(assetFlowQuery.data?.data, window, scope),
    [assetFlowQuery.data?.data, scope, window],
  );
  const currentFrame = useMemo(
    () => ({
      rawTokenItems: parsed.items,
      tokenItems: sortTokenItems(parsed.items),
    }),
    [parsed.items],
  );
  const cachedFrame = lastReadyFrames.current.get(cacheKey);
  const shouldUseCachedFrame =
    !parsed.error &&
    Boolean(cachedFrame) &&
    (projectionPending ||
      (assetFlowQuery.isFetching &&
        currentFrame.tokenItems.length === 0 &&
        !assetFlowQuery.isPending));
  const displayedFrame = shouldUseCachedFrame && cachedFrame ? cachedFrame : currentFrame;
  const rawTokenItems = displayedFrame.rawTokenItems;
  const tokenItems = displayedFrame.tokenItems;
  const marketTargets = useMemo(
    () =>
      rawTokenItems.flatMap((item) => {
        const target = targetRefFromTokenItem(item);
        return target ? [target] : [];
      }),
    [rawTokenItems],
  );
  const decisionCounts = useMemo(() => countDecisions(tokenItems), [tokenItems]);
  const assetFlowError =
    assetFlowQuery.error instanceof Error
      ? assetFlowQuery.error
      : parsed.error instanceof Error
        ? parsed.error
        : null;
  const isAssetFlowLoading =
    !assetFlowError &&
    tokenItems.length === 0 &&
    (assetFlowQuery.isPending || assetFlowQuery.fetchStatus === "fetching" || projectionPending);
  const isAssetFlowRefreshing =
    !assetFlowError && tokenItems.length > 0 && (assetFlowQuery.isFetching || projectionPending);

  useEffect(() => {
    if (parsed.error || projectionPending || currentFrame.tokenItems.length === 0) {
      return;
    }
    lastReadyFrames.current.set(cacheKey, currentFrame);
  }, [cacheKey, currentFrame, parsed.error, projectionPending]);

  return {
    assetFlowError,
    decisionCounts,
    isAssetFlowLoading,
    isAssetFlowRefreshing,
    marketTargets,
    projectionStatus,
    tokenItems,
  };
}

function parseTokenRadarItems(
  data: AssetFlowData | null | undefined,
  window: WindowKey,
  scope: ScopeKey,
): { items: TokenFlowItem[]; error: Error | null } {
  try {
    return { items: tokenRadarItems(data, window, scope), error: null };
  } catch (error) {
    return {
      items: [],
      error:
        error instanceof Error ? error : new Error("Token Radar response could not be parsed."),
    };
  }
}
