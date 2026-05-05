import type { SignalLabChain, SignalLabChainsData, SignalLabStage, SignalLabStageFilter } from "../api/types";
import { SIGNAL_LAB_STAGES, SIGNAL_LAB_STAGE_COPY, stageCount } from "../lib/signalLabChains";
import { SignalChainList } from "./SignalChainList";

type SignalLabWorkbenchProps = {
  data?: SignalLabChainsData;
  assetFilter: string;
  handleFilter: string;
  hasNextPage?: boolean;
  horizon: "6h" | "24h";
  isFetchingNextPage?: boolean;
  isLoading?: boolean;
  searchFilter: string;
  selectedChainId?: string | null;
  stageFilter: SignalLabStageFilter;
  onAssetChange: (asset: string) => void;
  onHandleChange: (handle: string) => void;
  onHorizonChange: (horizon: "6h" | "24h") => void;
  onLoadMore: () => void;
  onSearchChange: (search: string) => void;
  onSelect: (chain: SignalLabChain) => void;
  onStageChange: (stage: SignalLabStageFilter) => void;
};

export function SignalLabWorkbench({
  assetFilter,
  data,
  handleFilter,
  hasNextPage,
  horizon,
  isFetchingNextPage,
  isLoading,
  searchFilter,
  selectedChainId,
  stageFilter,
  onAssetChange,
  onHandleChange,
  onHorizonChange,
  onLoadMore,
  onSearchChange,
  onSelect,
  onStageChange
}: SignalLabWorkbenchProps) {
  return (
    <section className="signal-lab-workbench">
      <header className="signal-lab-workbench-head">
        <div>
          <h2>Signal Lab</h2>
          <p>Audit watched-account social events into snapshots, outcomes, and predictive credit.</p>
        </div>
      </header>

      <div className="signal-stage-grid" aria-label="Signal Lab lifecycle stages">
        {SIGNAL_LAB_STAGES.map((stage) => (
          <button
            className={stageFilter === stage ? "active" : ""}
            key={stage}
            type="button"
            onClick={() => onStageChange(stageFilter === stage ? "all" : stage)}
          >
            <span>{SIGNAL_LAB_STAGE_COPY[stage].label}</span>
            <b>{stageCount(data?.summary, stage)}</b>
            <em>{SIGNAL_LAB_STAGE_COPY[stage].description}</em>
          </button>
        ))}
      </div>

      <div className="signal-filter-bar" aria-label="Signal Lab filters">
        <div className="filter-cell signal-stage-filter">
          <span>Stage</span>
          <b>{stageFilter === "all" ? "All stages" : SIGNAL_LAB_STAGE_COPY[stageFilter as SignalLabStage].label}</b>
        </div>
        <div className="filter-cell signal-horizon-filter">
          <span>Horizon</span>
          <div className="signal-horizon-control" aria-label="settlement horizon">
            {(["6h", "24h"] as const).map((item) => (
              <button className={horizon === item ? "active" : ""} key={item} type="button" onClick={() => onHorizonChange(item)}>
                {item}
              </button>
            ))}
          </div>
        </div>
        <FilterField
          label="Asset"
          ariaLabel="Signal Lab asset filter"
          value={assetFilter}
          placeholder="$BNB"
          onChange={onAssetChange}
        />
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
          placeholder="build on BNB"
          onChange={onSearchChange}
        />
        <div className="filter-cell signal-sort-cell">
          <span>Sort</span>
          <b>Newest</b>
        </div>
      </div>

      <section className="signal-chain-workbench-list">
        <header>
          <h3>Signal Chains</h3>
          <span>{stageFilter === "all" ? "all stages" : SIGNAL_LAB_STAGE_COPY[stageFilter as SignalLabStage].label}</span>
        </header>
        <SignalChainList isLoading={isLoading} items={data?.items ?? []} selectedChainId={selectedChainId} onSelect={onSelect} />
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
