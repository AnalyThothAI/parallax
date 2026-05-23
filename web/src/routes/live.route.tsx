import { LivePage, LiveRadar } from "@features/live";
import {
  buildLiveSignalTapeItems,
  useLiveRadarRouteData,
  useLiveRecentQuery,
} from "@features/live/shell";
import { useSignalLabCompactQuery } from "@features/signal-lab/shell";
import type { LivePayload } from "@lib/types";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import { useMemo, type ReactNode } from "react";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();
  const recentQuery = useLiveRecentQuery({
    enabled: true,
    handles: context.liveRouteHandles,
    scope: context.scope,
    token: context.token,
  });
  const liveRadar = useLiveRadarRouteData({
    enabled: true,
    scope: context.scope,
    token: context.token,
    window: context.windowKey,
  });
  const signalLabCompact = useSignalLabCompactQuery({
    enabled: true,
    token: context.token,
  });
  const socketSnapshot = useSocketSnapshot();
  const recentReplayItems = recentQuery.data?.data.items;
  const liveItems = useMemo(
    () => mergeLiveItems(recentReplayItems ?? [], socketSnapshot.eventItems),
    [recentReplayItems, socketSnapshot.eventItems],
  );
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems: liveRadar.tokenItems }),
    [liveItems, liveRadar.tokenItems],
  );

  return (
    <LivePage
      hiddenSignalLabPulseData={signalLabCompact.hiddenSignalPulseData}
      hiddenSignalPulseLoading={signalLabCompact.hiddenSignalPulseLoading}
      isRecentLoading={recentQuery.isPending}
      liveSignalTapeItems={liveSignalTapeItems}
      mobileTask={context.mobileTask}
      selectedPulseItemId={context.selectedPulseItemId}
      selectedTapeEventId={context.selectedTapeEventId}
      signalLabPulseData={signalLabCompact.pulseData ?? null}
      signalPulseLoading={signalLabCompact.signalPulseColdLoading}
      socketStatus={socketSnapshot.status}
      onMobileTaskChange={context.onMobileTaskChange}
      onSelectPulse={context.selectPulseItem}
      onTapeSelect={context.onTapeSelect}
    >
      <LiveMarketSubscription targets={liveRadar.marketTargets}>
        <LiveRadar
          assetFlowError={liveRadar.assetFlowError}
          isAssetFlowLoading={liveRadar.isAssetFlowLoading}
          isAssetFlowRefreshing={liveRadar.isAssetFlowRefreshing}
          scope={context.scope}
          selectedTokenKey={null}
          tokenItems={liveRadar.tokenItems}
          windowKey={context.windowKey}
          onScopeChange={context.updateScope}
          onSelectToken={context.selectToken}
          onWindowChange={context.updateWindow}
        />
      </LiveMarketSubscription>
    </LivePage>
  );
}

function LiveMarketSubscription({
  children,
  targets,
}: {
  children: ReactNode;
  targets: Parameters<typeof useMarketSubscription>[0];
}) {
  useMarketSubscription(targets);
  return <>{children}</>;
}

function mergeLiveItems(replayItems: LivePayload[], eventItems: LivePayload[]): LivePayload[] {
  const byId = new Map<string, LivePayload>();
  for (const item of [...replayItems, ...eventItems]) {
    byId.set(item.event.event_id, item);
  }
  return [...byId.values()].sort(
    (left, right) =>
      Number(right.event.received_at_ms ?? 0) - Number(left.event.received_at_ms ?? 0),
  );
}
