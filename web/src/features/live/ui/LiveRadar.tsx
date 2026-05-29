import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import type { TokenRadarVenueFilter } from "@lib/venue";

import { TokenRadarTable } from "./TokenRadarTable";
import "./live.css";

type LiveRadarProps = {
  tokenItems: TokenFlowItem[];
  isAssetFlowLoading: boolean;
  isAssetFlowRefreshing?: boolean;
  assetFlowError: Error | null;
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
    <section className="mobile-task-surface" data-mobile-task-panel="radar">
      <TokenRadarTable
        error={assetFlowError}
        isLoading={isAssetFlowLoading}
        isRefreshing={isAssetFlowRefreshing}
        items={tokenItems}
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
