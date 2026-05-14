import { tokenKey } from "@lib/format";
import type { ScopeKey, TokenFlowItem, WindowKey } from "@lib/types";
import { RadarControls } from "@shared/ui/RadarControls";
import { RemoteState } from "@shared/ui/RemoteState";

import { TokenRadarRow } from "./TokenRadarRow";

type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  scope: ScopeKey;
  windowKey: WindowKey;
  isLoading: boolean;
  error?: Error | null;
  onSelect: (item: TokenFlowItem) => void;
  onOpenSearch: (item: TokenFlowItem) => void;
  onScopeChange: (scope: ScopeKey) => void;
  onWindowChange: (window: WindowKey) => void;
};

export function TokenRadarTable(props: TokenRadarTableProps) {
  const {
    items,
    selectedKey,
    scope,
    windowKey,
    isLoading,
    error,
    onSelect,
    onOpenSearch,
    onScopeChange,
    onWindowChange,
  } = props;
  const resultLabel = `${items.length} live ${items.length === 1 ? "case" : "cases"}`;

  return (
    <section className="radar-panel" aria-label="Token Radar">
      <header className="radar-toolbar">
        <div className="radar-scan-title">
          <h2>Token Radar</h2>
          <span>{resultLabel}</span>
        </div>
        <div className="toolbar-controls" aria-label="token radar scan controls">
          <RadarControls
            scope={scope}
            windowKey={windowKey}
            onScopeChange={onScopeChange}
            onWindowChange={onWindowChange}
          />
        </div>
      </header>

      <div className="token-radar-table">
        <div className="radar-head" aria-hidden="true">
          <span>Token case</span>
          <span>Social</span>
          <span>Why now</span>
          <span>Market</span>
          <span>Score</span>
        </div>
        {isLoading ? <RadarSkeleton /> : null}
        {error ? <RemoteState.Error error={`Token Radar 暂不可用 · ${error.message}`} /> : null}
        {!isLoading && !error && items.length === 0 ? (
          <RemoteState.Empty title="当前窗口暂无可交易 token 热度" />
        ) : null}
        {!isLoading && !error
          ? items.map((item) => {
              const key = tokenKey(item);
              return (
                <TokenRadarRow
                  key={`${key}:${item.flow.window_start_ms ?? ""}`}
                  item={item}
                  selected={selectedKey === key}
                  onOpenSearch={onOpenSearch}
                  onSelect={onSelect}
                />
              );
            })
          : null}
      </div>
    </section>
  );
}

function RadarSkeleton() {
  return (
    <div className="radar-skeleton" aria-label="loading token radar">
      {Array.from({ length: 8 }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}
