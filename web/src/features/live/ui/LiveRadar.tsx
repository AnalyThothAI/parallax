import type { RadarSortMode, ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { RadarControls } from "@shared/ui/RadarControls";

import { TokenRadarTable } from "./TokenRadarTable";

type LiveRadarProps = {
  tokenItems: TokenFlowItem[];
  isAssetFlowLoading: boolean;
  assetFlowError: Error | null;
  selectedTokenKey: string | null;
  radarSortMode: RadarSortMode;
  onSelectToken: (item: TokenFlowItem) => void;
  onOpenTokenSearch: (item: TokenFlowItem) => void;
  onSortModeChange: (mode: RadarSortMode) => void;
  scope: ScopeKey;
  windowKey: WindowKey;
  onScopeChange: (scope: ScopeKey) => void;
  onWindowChange: (window: WindowKey) => void;
};

export function LiveRadar({
  tokenItems,
  isAssetFlowLoading,
  assetFlowError,
  selectedTokenKey,
  radarSortMode,
  onSelectToken,
  onOpenTokenSearch,
  onSortModeChange,
  scope,
  windowKey,
  onScopeChange,
  onWindowChange,
}: LiveRadarProps) {
  return (
    <section className="mobile-task-surface" data-mobile-task-panel="radar">
      <div className="radar-control-row">
        <RadarControls
          scope={scope}
          windowKey={windowKey}
          onScopeChange={onScopeChange}
          onWindowChange={onWindowChange}
        />
      </div>

      <TokenRadarTable
        error={assetFlowError}
        isLoading={isAssetFlowLoading}
        items={tokenItems}
        selectedKey={selectedTokenKey}
        sortMode={radarSortMode}
        onOpenSearch={onOpenTokenSearch}
        onSelect={onSelectToken}
        onSortModeChange={onSortModeChange}
      />
    </section>
  );
}
