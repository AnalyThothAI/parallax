import { tokenKey } from "@lib/format";
import type { RadarSortMode, TokenFlowItem } from "@lib/types";
import { RemoteState } from "@shared/ui/RemoteState";

import { TokenRadarRow } from "./TokenRadarRow";

const SORT_LABELS: Array<{ mode: RadarSortMode; label: string }> = [
  { mode: "opportunity", label: "Desk pick" },
  { mode: "heat", label: "Attention" },
  { mode: "quality", label: "Proof" },
  { mode: "propagation", label: "Reach" },
  { mode: "timing", label: "Entry" },
];

type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  sortMode: RadarSortMode;
  isLoading: boolean;
  error?: Error | null;
  onSelect: (item: TokenFlowItem) => void;
  onOpenSearch: (item: TokenFlowItem) => void;
  onSortModeChange: (mode: RadarSortMode) => void;
};

export function TokenRadarTable({
  items,
  selectedKey,
  sortMode,
  isLoading,
  error,
  onSelect,
  onOpenSearch,
  onSortModeChange,
}: TokenRadarTableProps) {
  return (
    <section className="radar-panel" aria-label="Token Radar">
      <header className="radar-toolbar">
        <div>
          <h2>Token Radar</h2>
          <p>快速扫“这是什么、谁在推、为什么现在、能不能行动”。</p>
        </div>
        <div className="toolbar-controls" aria-label="token radar toolbar">
          <div className="segmented sort-toggle" aria-label="token radar sort">
            {SORT_LABELS.map((item) => (
              <button
                key={item.mode}
                className={sortMode === item.mode ? "active" : ""}
                onClick={() => onSortModeChange(item.mode)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="token-radar-table">
        <div className="radar-head">
          <span>Token case</span>
          <span>Official</span>
          <span>Community</span>
          <span>Narrative</span>
          <span>Market</span>
          <span>Decision</span>
          <span>Actions</span>
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
