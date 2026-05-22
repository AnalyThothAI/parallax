import { LivePage, LiveRadar } from "@features/live";
import { useMarketSubscription } from "@shared/socket/useMarketSubscription";
import type { ReactNode } from "react";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();

  return (
    <LivePage
      hiddenSignalLabPulseData={context.hiddenSignalLabPulseData}
      hiddenSignalPulseLoading={context.hiddenSignalPulseLoading}
      isRecentLoading={context.isRecentLoading}
      liveSignalTapeItems={context.liveSignalTapeItems}
      mobileTask={context.mobileTask}
      selectedPulseItemId={context.selectedPulseItemId}
      selectedTapeEventId={context.selectedTapeEventId}
      signalLabPulseData={context.signalLabPulseData}
      signalPulseLoading={context.signalPulseLoading}
      socketStatus={context.socketStatus}
      onMobileTaskChange={context.onMobileTaskChange}
      onSelectPulse={context.selectPulseItem}
      onTapeSelect={context.onTapeSelect}
    >
      <LiveMarketSubscription targets={context.marketTargets}>
        <LiveRadar
          assetFlowError={context.assetFlowError}
          isAssetFlowLoading={context.isAssetFlowLoading}
          isAssetFlowRefreshing={context.isAssetFlowRefreshing}
          scope={context.scope}
          selectedTokenKey={null}
          tokenItems={context.tokenItems}
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
