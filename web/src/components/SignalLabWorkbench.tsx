import type { TradingAttentionData, TradingAttentionItem, TradingAttentionKind, TradingAttentionKindFilter } from "../api/types";
import { TradingAttentionList } from "./SignalLabPulse";

const ATTENTION_KINDS: Array<{ kind: TradingAttentionKind; label: string; description: string }> = [
  { kind: "direct_token", label: "Direct token", description: "Concrete token, CA, or ticker attention." },
  { kind: "topic_heat", label: "Topic heat", description: "Keyword or meme attention without forced tokenization." },
  { kind: "ecosystem_signal", label: "Ecosystem", description: "Chain, sector, or product direction." },
  { kind: "market_structure", label: "Structure", description: "Positioning, liquidity, and regime comments." },
  { kind: "risk_alert", label: "Risk", description: "Regulation, exchange, contract, or market risk." }
];

type SignalLabWorkbenchProps = {
  data?: TradingAttentionData;
  handleFilter: string;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
  isLoading?: boolean;
  kindFilter: TradingAttentionKindFilter;
  searchFilter: string;
  selectedItemId?: string | null;
  onHandleChange: (handle: string) => void;
  onKindChange: (kind: TradingAttentionKindFilter) => void;
  onLoadMore: () => void;
  onSearchChange: (search: string) => void;
  onSelect: (item: TradingAttentionItem) => void;
};

export function SignalLabWorkbench({
  data,
  handleFilter,
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  kindFilter,
  searchFilter,
  selectedItemId,
  onHandleChange,
  onKindChange,
  onLoadMore,
  onSearchChange,
  onSelect
}: SignalLabWorkbenchProps) {
  return (
    <section className="signal-lab-workbench">
      <header className="signal-lab-workbench-head">
        <div>
          <h2>Signal Lab</h2>
          <p>Track watched-account trading attention across direct tokens, topics, ecosystems, risk, and market structure.</p>
        </div>
      </header>

      <div className="signal-stage-grid" aria-label="Trading attention categories">
        {ATTENTION_KINDS.map((item) => (
          <button
            className={kindFilter === item.kind ? "active" : ""}
            key={item.kind}
            type="button"
            onClick={() => onKindChange(kindFilter === item.kind ? "all" : item.kind)}
          >
            <span>{item.label}</span>
            <b>{data?.summary[item.kind] ?? 0}</b>
            <em>{item.description}</em>
          </button>
        ))}
      </div>

      <div className="signal-filter-bar" aria-label="Signal Lab filters">
        <div className="filter-cell signal-stage-filter">
          <span>Kind</span>
          <b>{kindFilter === "all" ? "All attention" : ATTENTION_KINDS.find((item) => item.kind === kindFilter)?.label}</b>
        </div>
        <FilterField
          label="Source"
          ariaLabel="Signal Lab source filter"
          value={handleFilter}
          placeholder="@cz_binance"
          onChange={onHandleChange}
        />
        <FilterField
          label="Search"
          ariaLabel="Signal Lab text filter"
          value={searchFilter}
          placeholder="grok, build, solana"
          onChange={onSearchChange}
        />
        <div className="filter-cell signal-sort-cell">
          <span>Sort</span>
          <b>Heat</b>
        </div>
      </div>

      <section className="signal-chain-workbench-list">
        <header>
          <h3>Trading Attention</h3>
          <span>{kindFilter === "all" ? "all categories" : ATTENTION_KINDS.find((item) => item.kind === kindFilter)?.label}</span>
        </header>
        <TradingAttentionList isLoading={isLoading} items={data?.items ?? []} selectedItemId={selectedItemId} onSelect={onSelect} />
        {hasNextPage ? (
          <button className="signal-load-more" disabled={isFetchingNextPage} type="button" onClick={onLoadMore}>
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        ) : null}
      </section>
    </section>
  );
}

function FilterField({
  ariaLabel,
  label,
  onChange,
  placeholder,
  value
}: {
  ariaLabel: string;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="filter-cell signal-filter-cell">
      <span>{label}</span>
      <input aria-label={ariaLabel} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
