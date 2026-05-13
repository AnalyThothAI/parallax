import { useEffect, useMemo } from "react";

import { normalizeMarketTargets } from "./marketTargets";
import { useSocketRegistry } from "./socketContext";
import type { MarketTargetRef } from "./socketTypes";

export function useMarketSubscription(targets: MarketTargetRef[]) {
  const registerMarketTargets = useSocketRegistry();
  const normalizedTargets = useMemo(() => normalizeMarketTargets(targets), [targets]);
  const targetKey = useMemo(() => JSON.stringify(normalizedTargets), [normalizedTargets]);

  useEffect(() => {
    if (!registerMarketTargets) {
      return undefined;
    }
    const parsedTargets = JSON.parse(targetKey) as MarketTargetRef[];
    return registerMarketTargets(parsedTargets);
  }, [registerMarketTargets, targetKey]);
}
