import type { AttentionFrontierItem, Decision, RadarSortMode, TokenFlowItem } from "../api/types";
import { TokenRadarRow } from "./TokenRadarRow";

const SORT_LABELS: Array<{ mode: RadarSortMode; label: string }> = [
  { mode: "opportunity", label: "Opportunity" },
  { mode: "heat", label: "Heat" },
  { mode: "quality", label: "Quality" },
  { mode: "propagation", label: "Propagation" },
  { mode: "timing", label: "Timing" }
];

type TokenRadarTableProps = {
  items: TokenFlowItem[];
  selectedKey: string | null;
  manualDecisions: Record<string, Decision>;
  sortMode: RadarSortMode;
  isLoading: boolean;
  error?: Error | null;
  frontierByToken: Map<string, AttentionFrontierItem>;
  onSelect: (item: TokenFlowItem) => void;
  onSortModeChange: (mode: RadarSortMode) => void;
};

export function TokenRadarTable({
  items,
  selectedKey,
  manualDecisions,
  sortMode,
  isLoading,
  error,
  frontierByToken,
  onSelect,
  onSortModeChange
}: TokenRadarTableProps) {
  return (
    <section className="radar-panel" aria-label="Token Radar">
      <header className="radar-toolbar">
        <div>
          <h2>Token Radar</h2>
          <span>
            TOKEN RADAR <b>{items.length}</b>
          </span>
        </div>
        <div className="toolbar-controls">
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
          <span>Token</span>
          <span>Heat</span>
          <span>Quality</span>
          <span>Propagation</span>
          <span>Market</span>
          <span>Timing</span>
          <span>Decision</span>
        </div>
        {isLoading ? <RadarSkeleton /> : null}
        {error ? <div className="table-state">Token Radar 暂不可用 · {error.message}</div> : null}
        {!isLoading && !error && items.length === 0 ? <div className="table-state">当前窗口暂无可交易 token 热度</div> : null}
        {!isLoading && !error
          ? items.map((item) => {
              const key = tokenDecisionKey(item);
              const manualDecision = manualDecisions[key];
              return (
                <TokenRadarRow
                  key={`${key}:${item.flow.window_start_ms ?? ""}`}
                  item={item}
                  selected={selectedKey === key}
                  decision={manualDecision ?? item.opportunity.decision}
                  manualDecision={manualDecision}
                  narrativeLink={frontierMatchForToken(item, frontierByToken)}
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

function tokenDecisionKey(item: TokenFlowItem): string {
  return item.identity.token_id ?? item.identity.address ?? item.identity.identity_key;
}

function frontierMatchForToken(
  item: TokenFlowItem,
  frontierByToken: Map<string, AttentionFrontierItem>
): AttentionFrontierItem | undefined {
  for (const key of frontierTokenKeys(item.identity)) {
    const match = frontierByToken.get(key);
    if (match) {
      return match;
    }
  }
  return undefined;
}

function frontierTokenKeys(identity: TokenFlowItem["identity"]): string[] {
  return [
    `identity:${identity.identity_key}`,
    identity.token_id ? `token:${identity.token_id}` : "",
    identity.address ? `address:${identity.address.toLowerCase()}` : "",
    identity.symbol ? `symbol:${identity.symbol.toUpperCase()}` : ""
  ].filter(Boolean);
}
