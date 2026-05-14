import { eventHandle, eventText, formatRelativeTime } from "@lib/format";
import type {
  LivePayload,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStatus,
  SignalPulseStatusFilter,
} from "@lib/types";
import { RemoteState, SkeletonRows } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { useId } from "react";

import { SignalPulseQueue } from "./SignalPulseQueue";

const PULSE_STATUSES: Array<{ status: SignalPulseStatus; label: string; description: string }> = [
  {
    status: "trade_candidate",
    label: "交易候选",
    description: "热度和市场状态足够进入详情核验。",
  },
  {
    status: "token_watch",
    label: "代币观察",
    description: "标的热度出现，但还缺少确认。",
  },
  {
    status: "risk_rejected_high_info",
    label: "已拒绝",
    description: "信息量高，但被风控条件拦下。",
  },
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
  onStatusChange,
}: SignalLabWorkbenchProps) {
  const items = data?.items ?? [];
  const summary = overviewData?.summary ?? data?.summary;
  const health = overviewData?.health ?? data?.health;
  const hasActiveFilters =
    statusFilter !== "all" || Boolean(handleFilter.trim()) || Boolean(searchFilter.trim());
  const hasAccountLens = Boolean(handleFilter.trim()) && !searchFilter.trim();
  const showAccountEvents =
    !isLoading &&
    !items.length &&
    hasAccountLens &&
    (Boolean(isAccountEventsLoading) || accountEvents.length > 0);
  const statusLabel = statusFilter === "all" ? "all statuses" : labelForStatus(statusFilter);
  const totalPulse = totalByStatus(summary);
  return (
    <section className="signal-lab-workbench">
      <header className="signal-lab-workbench-head">
        <div>
          <h2>Signal Pulse</h2>
        </div>
        <div className="signal-lab-workbench-state">
          <span>
            窗口 <b>{windowLabel}</b>
          </span>
          <span>
            候选 <b>{health?.candidate_count ?? totalPulse}</b>
          </span>
          <span>
            当前 <b>{items.length}</b>
          </span>
        </div>
      </header>

      <div className="signal-stage-grid" aria-label="Signal Pulse candidate stages">
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

      <div className="signal-filter-bar" aria-label="Signal Pulse candidate filters">
        <div className="filter-cell signal-stage-filter">
          <span>状态</span>
          <b>
            {statusFilter === "all"
              ? "全部候选"
              : PULSE_STATUSES.find((item) => item.status === statusFilter)?.label}
          </b>
        </div>
        <FilterField
          label="来源账号"
          ariaLabel="Signal Pulse source filter"
          value={handleFilter}
          placeholder="@cz_binance"
          onChange={onHandleChange}
        />
        <FilterField
          label="标的"
          ariaLabel="Signal Pulse identity filter"
          value={searchFilter}
          placeholder="BNB, token:SOL"
          onChange={onSearchChange}
        />
        <div className="filter-cell signal-sort-cell">
          <span>排序</span>
          <b>最新</b>
        </div>
        <button
          className="signal-clear-filters"
          disabled={!hasActiveFilters}
          type="button"
          onClick={onClearFilters}
        >
          重置
        </button>
      </div>

      <section className="signal-pulse-workbench-list">
        <header>
          <h3>{showAccountEvents ? "账号事件" : "候选列表"}</h3>
          <span>
            {showAccountEvents
              ? `${accountEvents.length} 条 · 账号视角`
              : `${items.length} 条 · ${statusLabel}`}
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
          <SignalLabEmptyState
            hasActiveFilters={hasActiveFilters}
            onClearFilters={onClearFilters}
          />
        ) : (
          <SignalPulseQueue
            isLoading={isLoading}
            items={items}
            selectedItemId={selectedItemId}
            onSelect={onSelect}
          />
        )}
        {hasNextPage ? (
          <button
            className="signal-load-more"
            disabled={isFetchingNextPage}
            type="button"
            onClick={onLoadMore}
          >
            {isFetchingNextPage ? "加载中" : "加载更多"}
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
  onSelect,
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
          <article
            className={clsx(
              "signal-chain-row",
              selectedEventId === item.event.event_id && "selected",
            )}
            key={item.event.event_id}
          >
            <button
              aria-label={`查看关注账号事件 ${title}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className="signal-stage-badge account_event">
                {item.event.action ?? "post"}
              </span>
              <span className="signal-chain-main">
                <strong>@{eventHandle(item.event)}</strong>
                <em>关注账号 · {formatRelativeTime(item.event.received_at_ms)} 前</em>
                <p>{title}</p>
                <span className="signal-chain-chipline">
                  {chips.slice(0, 4).map((chip) => (
                    <span key={chip}>{chip}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{chips.length || "-"}</b>
                <small>{item.alerts.length ? "预警" : "实体"}</small>
              </span>
              <span className="signal-chain-time">
                {formatRelativeTime(item.event.received_at_ms)}
              </span>
            </button>
          </article>
        );
      })}
    </div>
  );
}

function SignalLabEmptyState({
  hasActiveFilters,
  onClearFilters,
}: {
  hasActiveFilters: boolean;
  onClearFilters: () => void;
}) {
  return (
    <RemoteState.Empty
      title={hasActiveFilters ? "没有匹配的 Signal Pulse 候选" : "当前窗口没有 Signal Pulse 候选"}
      action={
        hasActiveFilters ? (
          <button type="button" onClick={onClearFilters}>
            清除筛选
          </button>
        ) : null
      }
    />
  );
}

function accountEventChips(item: LivePayload): string[] {
  const values = [
    ...(item.event.cashtags ?? []).map((value) => `$${value}`),
    ...(item.event.hashtags ?? []).map((value) => `#${value}`),
    ...(item.event.mentions ?? []).map((value) => `@${value}`),
    ...item.entities.map((entity) => `${entity.entity_type}:${entity.normalized_value}`),
    ...item.alerts.map((alert) => alert.alert_type),
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
  if (status === "all") return "全部状态";
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
  value,
}: {
  ariaLabel: string;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  const inputId = useId();
  return (
    <label className="filter-cell signal-filter-cell" htmlFor={inputId}>
      <span>{label}</span>
      <input
        aria-label={ariaLabel}
        id={inputId}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
