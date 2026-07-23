import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import type { TokenRadarVenueFilter } from "@lib/venue";

import type { RadarStatusInput } from "../model/radarContentStatus";

import { TokenRadarTable } from "./TokenRadarTable";
import "./live.css";

type LiveRadarProps = {
  tokenItems: TokenFlowItem[];
  isAssetFlowLoading: boolean;
  isAssetFlowRefreshing?: boolean;
  assetFlowError: Error | null;
  radarStatus: RadarStatusInput;
  selectedTokenKey: string | null;
  onSelectToken: (item: TokenFlowItem) => void;
  scope: ScopeKey;
  windowKey: WindowKey;
  onScopeChange: (scope: ScopeKey) => void;
  onVenueChange: (venue: TokenRadarVenueFilter) => void;
  onWindowChange: (window: WindowKey) => void;
  venueFilter: TokenRadarVenueFilter;
};

export function LiveRadar({
  tokenItems,
  isAssetFlowLoading,
  isAssetFlowRefreshing = false,
  assetFlowError,
  radarStatus,
  selectedTokenKey,
  onSelectToken,
  scope,
  windowKey,
  onScopeChange,
  onVenueChange,
  onWindowChange,
  venueFilter,
}: LiveRadarProps) {
  return (
    <section className="live-radar-surface">
      <TokenRadarTable
        error={assetFlowError}
        isLoading={isAssetFlowLoading}
        isRefreshing={isAssetFlowRefreshing}
        items={tokenItems}
        radarStatus={radarStatus}
        scope={scope}
        selectedKey={selectedTokenKey}
        windowKey={windowKey}
        onScopeChange={onScopeChange}
        onSelect={onSelectToken}
        onVenueChange={onVenueChange}
        onWindowChange={onWindowChange}
        venueFilter={venueFilter}
      />
    </section>
  );
}
