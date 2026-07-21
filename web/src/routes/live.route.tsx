import { LivePage, LiveRadar } from "@features/live";
import {
  buildLiveSignalTapeItems,
  useLiveRadarRouteData,
  useLiveRecentQuery,
  useLiveSelection,
} from "@features/live/shell";
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
  const selection = useLiveSelection({ scope: context.scope });
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
      isRecentLoading={recentQuery.isPending}
      liveSignalTapeItems={liveSignalTapeItems}
      mobileTask={selection.mobileTask}
      selectedTapeEventId={selection.selectedTapeEventId}
      socketStatus={socketSnapshot.status}
      onMobileTaskChange={selection.handleMobileTaskChange}
      onTapeSelect={selection.handleTapeSelect}
    >
      <LiveMarketSubscription targets={liveRadar.marketTargets}>
        <LiveRadar
          assetFlowError={liveRadar.assetFlowError}
          isAssetFlowLoading={liveRadar.isAssetFlowLoading}
          isAssetFlowRefreshing={liveRadar.isAssetFlowRefreshing}
          scope={context.scope}
          selectedTokenKey={null}
          tokenItems={liveRadar.tokenItems}
          venueFilter={liveRadar.venueFilter}
          windowKey={context.windowKey}
          onScopeChange={context.updateScope}
          onSelectToken={selection.selectToken}
          onVenueChange={liveRadar.setVenueFilter}
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
