import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";

import { TokenRadarTable } from "./TokenRadarTable";
import "./live.css";

type LiveRadarProps = {
  tokenItems: TokenFlowItem[];
  isAssetFlowLoading: boolean;
  assetFlowError: Error | null;
  selectedTokenKey: string | null;
  onSelectToken: (item: TokenFlowItem) => void;
  onOpenTokenSearch: (item: TokenFlowItem) => void;
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
  onSelectToken,
  onOpenTokenSearch,
  scope,
  windowKey,
  onScopeChange,
  onWindowChange,
}: LiveRadarProps) {
  return (
    <section className="mobile-task-surface" data-mobile-task-panel="radar">
      <TokenRadarTable
        error={assetFlowError}
        isLoading={isAssetFlowLoading}
        items={tokenItems}
        scope={scope}
        selectedKey={selectedTokenKey}
        windowKey={windowKey}
        onOpenSearch={onOpenTokenSearch}
        onScopeChange={onScopeChange}
        onSelect={onSelectToken}
        onWindowChange={onWindowChange}
      />
    </section>
  );
}
