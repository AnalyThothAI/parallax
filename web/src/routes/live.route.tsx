import { LivePage, LiveRadar } from "@features/live";
import { useLiveRadarRouteData, useLiveSelection } from "@features/live/shell";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import type { ReactNode } from "react";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();
  const liveRadar = useLiveRadarRouteData({
    enabled: true,
    scope: context.scope,
    token: context.token,
    window: context.windowKey,
  });
  const selection = useLiveSelection({ scope: context.scope });

  return (
    <LivePage>
      <LiveMarketSubscription targets={liveRadar.marketTargets}>
        <LiveRadar
          assetFlowError={liveRadar.assetFlowError}
          isAssetFlowLoading={liveRadar.isAssetFlowLoading}
          isAssetFlowRefreshing={liveRadar.isAssetFlowRefreshing}
          radarStatus={liveRadar.radarStatus}
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
