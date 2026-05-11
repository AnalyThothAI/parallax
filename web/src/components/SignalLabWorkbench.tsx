import type { LivePayload, SignalPulseData, SignalPulseItem, SignalPulseStatus, SignalPulseStatusFilter } from "../api/types";
import { eventHandle, eventText, formatRelativeTime } from "../lib/format";
import { SkeletonRows } from "../shared/ui/RemoteState";
import { SignalPulseList } from "./SignalLabPulse";

const PULSE_STATUSES: Array<{ status: SignalPulseStatus; label: string; description: string }> = [
  { status: "trade_candidate", label: "Trade candidate", description: "Actionable setup with enough social and market context." },
  { status: "token_watch", label: "Token watch", description: "Token-specific signal that still needs confirmation." },
  { status: "theme_watch", label: "Theme watch", description: "Narrative or cluster worth monitoring." },
  { status: "risk_rejected_high_info", label: "Rejected high info", description: "Informative but rejected by gates." }
];

type SignalLabWorkbenchProps = {
  accountEvents?: LivePayload[];
  data?: SignalPulseData;
  handleFilter: string;
  hasNextPage?: boolean;
  isAccountEventsLoading?: boolean;
  isFetchingNextPage?: boolean;
  isLoading?: boolean;
  overviewData?: SignalPulseData;
  searchFilter: string;
  selectedAccountEventId?: string | null;
  selectedItemId?: string | null;
  statusFilter: SignalPulseStatusFilter;
  windowLabel: string;
  onClearFilters: () => void;
  onHandleChange: (handle: string) => void;
  onLoadMore: () => void;
  onSearchChange: (search: string) => void;
  onSelectAccountEvent: (item: LivePayload) => void;
  onSelect: (item: SignalPulseItem) => void;
  onStatusChange: (status: SignalPulseStatusFilter) => void;
};

export function SignalLabWorkbench({
  accountEvents = [],
  data,
  handleFilter,
  hasNextPage,
  isAccountEventsLoading,
  isFetchingNextPage,
  isLoading,
  overviewData,
  searchFilter,
  selectedAccountEventId,
  selectedItemId,
  statusFilter,
  windowLabel,
  onClearFilters,
  onHandleChange,
  onLoadMore,
  onSearchChange,
  onSelectAccountEvent,
  onSelect,
  onStatusChange
}: SignalLabWorkbenchProps) {
  const items = data?.items ?? [];
  const summary = overviewData?.summary ?? data?.summary;
  const health = overviewData?.health ?? data?.health;
  const hasActiveFilters = statusFilter !== "all" || Boolean(handleFilter.trim()) || Boolean(searchFilter.trim());
  const hasAccountLens = Boolean(handleFilter.trim()) && !searchFilter.trim();
  const showAccountEvents = !isLoading && !items.length && hasAccountLens && (Boolean(isAccountEventsLoading) || accountEvents.length > 0);
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
          <h3>{showAccountEvents ? "Watched account events" : "Signal Pulse"}</h3>
          <span>
            {showAccountEvents ? `${accountEvents.length} posts · account lens` : `${items.length} shown · ${statusLabel}`}
          </span>
        </header>
        {showAccountEvents ? (
          <AccountEventList
            isLoading={isAccountEventsLoading}
            items={accountEvents}
            selectedEventId={selectedAccountEventId}
            onSelect={onSelectAccountEvent}
          />
        ) : !isLoading && !items.length ? (
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

function AccountEventList({
  isLoading,
  items,
  selectedEventId,
  onSelect
}: {
  isLoading?: boolean;
  items: LivePayload[];
  selectedEventId?: string | null;
  onSelect: (item: LivePayload) => void;
}) {
  if (isLoading && !items.length) {
    return <SkeletonRows count={5} label="loading watched account events" />;
  }
  return (
    <div className="signal-chain-list signal-account-event-list">
      {items.map((item) => {
        const title = eventText(item.event) || "no text";
        const chips = accountEventChips(item);
        return (
          <article className={`signal-chain-row ${selectedEventId === item.event.event_id ? "selected" : ""}`} key={item.event.event_id}>
            <button
              aria-label={`open watched post ${title}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className="signal-stage-badge account_event">{item.event.action ?? "post"}</span>
              <span className="signal-chain-main">
                <strong>@{eventHandle(item.event)}</strong>
                <em>
                  watched · {formatRelativeTime(item.event.received_at_ms)} ago
                </em>
                <p>{title}</p>
                <span className="signal-chain-chipline">
                  {chips.slice(0, 4).map((chip) => (
                    <span key={chip}>{chip}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{chips.length || "-"}</b>
                <small>{item.alerts.length ? "alerts" : "entities"}</small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.event.received_at_ms)}</span>
            </button>
          </article>
        );
      })}
    </div>
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

function accountEventChips(item: LivePayload): string[] {
  const values = [
    ...(item.event.cashtags ?? []).map((value) => `$${value}`),
    ...(item.event.hashtags ?? []).map((value) => `#${value}`),
    ...(item.event.mentions ?? []).map((value) => `@${value}`),
    ...item.entities.map((entity) => `${entity.entity_type}:${entity.normalized_value}`),
    ...item.alerts.map((alert) => alert.alert_type)
  ];
  const seen = new Set<string>();
  return values.filter((value) => {
    if (!value || seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
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
