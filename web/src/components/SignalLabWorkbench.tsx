import type { SignalPulseData, SignalPulseItem, SignalPulseStatus, SignalPulseStatusFilter } from "../api/types";
import { SignalPulseList } from "./SignalLabPulse";

const PULSE_STATUSES: Array<{ status: SignalPulseStatus; label: string; description: string }> = [
  { status: "trade_candidate", label: "Trade candidate", description: "Actionable setup with enough social and market context." },
  { status: "token_watch", label: "Token watch", description: "Token-specific signal that still needs confirmation." },
  { status: "theme_watch", label: "Theme watch", description: "Narrative or cluster worth monitoring." },
  { status: "risk_rejected_high_info", label: "Rejected high info", description: "Informative but rejected by gates." }
];

type SignalLabWorkbenchProps = {
  data?: SignalPulseData;
  handleFilter: string;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
  isLoading?: boolean;
  overviewData?: SignalPulseData;
  searchFilter: string;
  selectedItemId?: string | null;
  statusFilter: SignalPulseStatusFilter;
  windowLabel: string;
  onClearFilters: () => void;
  onHandleChange: (handle: string) => void;
  onLoadMore: () => void;
  onSearchChange: (search: string) => void;
  onSelect: (item: SignalPulseItem) => void;
  onStatusChange: (status: SignalPulseStatusFilter) => void;
};

export function SignalLabWorkbench({
  data,
  handleFilter,
  hasNextPage,
  isFetchingNextPage,
  isLoading,
  overviewData,
  searchFilter,
  selectedItemId,
  statusFilter,
  windowLabel,
  onClearFilters,
  onHandleChange,
  onLoadMore,
  onSearchChange,
  onSelect,
  onStatusChange
}: SignalLabWorkbenchProps) {
  const items = data?.items ?? [];
  const summary = overviewData?.summary ?? data?.summary;
  const health = overviewData?.health ?? data?.health;
  const hasActiveFilters = statusFilter !== "all" || Boolean(handleFilter.trim()) || Boolean(searchFilter.trim());
  const statusLabel = statusFilter === "all" ? "all statuses" : labelForStatus(statusFilter);
  const totalPulse = totalByStatus(summary);
  return (
    <section className="signal-lab-workbench">
      <header className="signal-lab-workbench-head">
        <div>
          <h2>Signal Lab</h2>
          <p>Review Signal Pulse agent candidates by status, source, and query.</p>
        </div>
        <div className="signal-lab-workbench-state">
          <span>
            window <b>{windowLabel}</b>
          </span>
          <span>
            candidates <b>{health?.candidate_count ?? totalPulse}</b>
          </span>
          <span>
            shown <b>{items.length}</b>
          </span>
        </div>
      </header>

      <div className="signal-stage-grid" aria-label="Signal Pulse statuses">
        {PULSE_STATUSES.map((item) => (
          <button
            className={statusFilter === item.status ? "active" : ""}
            key={item.status}
            type="button"
            onClick={() => onStatusChange(statusFilter === item.status ? "all" : item.status)}
          >
            <span>{item.label}</span>
            <b>{summary?.[item.status] ?? 0}</b>
            <em>{item.description}</em>
          </button>
        ))}
      </div>

      <div className="signal-filter-bar" aria-label="Signal Lab filters">
        <div className="filter-cell signal-stage-filter">
          <span>Status</span>
          <b>{statusFilter === "all" ? "All pulse" : PULSE_STATUSES.find((item) => item.status === statusFilter)?.label}</b>
        </div>
        <FilterField
          label="Source"
          ariaLabel="Signal Lab source filter"
          value={handleFilter}
          placeholder="@cz_binance"
          onChange={onHandleChange}
        />
        <FilterField
          label="Symbol/target"
          ariaLabel="Signal Lab identity filter"
          value={searchFilter}
          placeholder="BNB, token:SOL, asset:..."
          onChange={onSearchChange}
        />
        <div className="filter-cell signal-sort-cell">
          <span>Sort</span>
          <b>Updated</b>
        </div>
        <button className="signal-clear-filters" disabled={!hasActiveFilters} type="button" onClick={onClearFilters}>
          Reset
        </button>
      </div>

      <section className="signal-chain-workbench-list">
        <header>
          <h3>Signal Pulse</h3>
          <span>
            {items.length} shown · {statusLabel}
          </span>
        </header>
        {!isLoading && !items.length ? (
          <SignalLabEmptyState hasActiveFilters={hasActiveFilters} onClearFilters={onClearFilters} />
        ) : (
          <SignalPulseList isLoading={isLoading} items={items} selectedItemId={selectedItemId} onSelect={onSelect} />
        )}
        {hasNextPage ? (
          <button className="signal-load-more" disabled={isFetchingNextPage} type="button" onClick={onLoadMore}>
            {isFetchingNextPage ? "Loading..." : "Load more"}
          </button>
        ) : null}
      </section>
    </section>
  );
}

function SignalLabEmptyState({ hasActiveFilters, onClearFilters }: { hasActiveFilters: boolean; onClearFilters: () => void }) {
  return (
    <div className="signal-empty-panel">
      <b>{hasActiveFilters ? "No matching Signal Pulse items" : "No Signal Pulse items in this window"}</b>
      {hasActiveFilters ? (
        <button type="button" onClick={onClearFilters}>
          Clear filters
        </button>
      ) : null}
    </div>
  );
}

function labelForStatus(status: SignalPulseStatusFilter): string {
  if (status === "all") return "all statuses";
  return PULSE_STATUSES.find((item) => item.status === status)?.label ?? status;
}

function totalByStatus(summary?: SignalPulseData["summary"]): number {
  if (!summary) return 0;
  return PULSE_STATUSES.reduce((total, item) => total + Number(summary[item.status] ?? 0), 0);
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
