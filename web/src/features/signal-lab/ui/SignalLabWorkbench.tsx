import { eventHandle, eventText, formatRelativeTime } from "@lib/format";
import type {
  LivePayload,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStatus,
  SignalPulseStatusFilter,
  SignalPulseVisibilityFilter,
} from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import * as Tabs from "@shared/ui/tabs";
import clsx from "clsx";
import { useId } from "react";

import { SignalPulseQueue } from "./SignalPulseQueue";
import "./SignalLabChainList.css";
import "./SignalLabWorkbench.css";

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
  visibilityFilter: SignalPulseVisibilityFilter;
  windowLabel: string;
  onClearFilters: () => void;
  onHandleChange: (handle: string) => void;
  onLoadMore: () => void;
  onSearchChange: (search: string) => void;
  onSelectAccountEvent: (item: LivePayload) => void;
  onSelect: (item: SignalPulseItem) => void;
  onStatusChange: (status: SignalPulseStatusFilter) => void;
  onVisibilityChange: (visibility: SignalPulseVisibilityFilter) => void;
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
  visibilityFilter,
  windowLabel,
  onClearFilters,
  onHandleChange,
  onLoadMore,
  onSearchChange,
  onSelectAccountEvent,
  onSelect,
  onStatusChange,
  onVisibilityChange,
}: SignalLabWorkbenchProps) {
  const items = data?.items ?? [];
  const summary = overviewData?.summary ?? data?.summary;
  const health = overviewData?.health ?? data?.health;
  const totalPulse = totalByStatus(summary);
  const publicCount = Number(health?.public_candidate_count ?? totalPulse);
  const hiddenCount = Number(
    health?.hidden_candidate_count ??
      Math.max(0, Number(health?.candidate_count ?? 0) - publicCount),
  );
  const hasActiveFilters =
    visibilityFilter !== "public" ||
    (visibilityFilter === "public" && statusFilter !== "all") ||
    Boolean(handleFilter.trim()) ||
    Boolean(searchFilter.trim());
  const hasAccountLens = Boolean(handleFilter.trim()) && !searchFilter.trim();
  const showAccountEvents =
    !isLoading &&
    !items.length &&
    hasAccountLens &&
    visibilityFilter === "public" &&
    (Boolean(isAccountEventsLoading) || accountEvents.length > 0);
  const statusLabel =
    visibilityFilter === "hidden"
      ? "隐藏候选"
      : statusFilter === "all"
        ? "all statuses"
        : labelForStatus(statusFilter);
  const healthNotice = buildPulseHealthNotice(health);
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

      <VisibilityTabs
        hiddenCount={hiddenCount}
        publicCount={publicCount}
        value={visibilityFilter}
        onChange={onVisibilityChange}
      />

      {visibilityFilter === "public" ? (
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
      ) : null}

      <div className="signal-filter-bar" aria-label="Signal Pulse candidate filters">
        <div className="filter-cell signal-stage-filter">
          <span>状态</span>
          <b>
            {visibilityFilter === "hidden"
              ? "隐藏候选"
              : statusFilter === "all"
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

      {healthNotice ? (
        <div
          aria-label="Signal Pulse health"
          className={clsx("signal-pulse-health-banner", healthNotice.tone)}
          role="status"
        >
          <strong>{healthNotice.title}</strong>
          <span>{healthNotice.detail}</span>
          <em>{healthNotice.meta}</em>
        </div>
      ) : null}

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
    return <PageState.TableSkeleton rows={5} label="loading watched account events" />;
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
    <PageState.Empty
      title={hasActiveFilters ? "没有匹配的 Signal Pulse 候选" : "当前窗口没有 Signal Pulse 候选"}
      action={
        hasActiveFilters ? (
          <Button size="sm" type="button" variant="outline" onClick={onClearFilters}>
            清除筛选
          </Button>
        ) : null
      }
    />
  );
}

function VisibilityTabs({
  hiddenCount,
  publicCount,
  value,
  onChange,
}: {
  hiddenCount: number;
  publicCount: number;
  value: SignalPulseVisibilityFilter;
  onChange: (visibility: SignalPulseVisibilityFilter) => void;
}) {
  return (
    <Tabs.Root
      className="signal-visibility-tabs"
      value={value}
      activationMode="manual"
      onValueChange={(next) => onChange(next as SignalPulseVisibilityFilter)}
    >
      <Tabs.List aria-label="Signal Pulse visibility" className="signal-visibility-tab-list">
        <Tabs.Trigger value="public">
          <span>公开</span>
          <b>{publicCount}</b>
        </Tabs.Trigger>
        <Tabs.Trigger value="hidden">
          <span>隐藏</span>
          <b>{hiddenCount}</b>
        </Tabs.Trigger>
      </Tabs.List>
    </Tabs.Root>
  );
}

function buildPulseHealthNotice(health: SignalPulseData["health"] | null | undefined) {
  if (!health) {
    return null;
  }
  const publishStatus = String(health.publish_status ?? "healthy");
  const publicReady = health.public_ready ?? health.pulse_ready;
  const hiddenHold = Number(health.hidden_hold_publish_4h ?? 0);
  const publicCount = Number(health.public_candidate_count ?? health.public_candidates_4h ?? 0);
  const shouldShow =
    publishStatus === "hold_publish" ||
    publishStatus === "degraded" ||
    (!publicReady && hiddenHold > 0);
  if (!shouldShow) {
    return null;
  }
  const reason = health.reasons?.[0] ? cleanHealthReason(health.reasons[0]) : "health gate active";
  const title =
    publishStatus === "hold_publish"
      ? "发布暂停"
      : publishStatus === "degraded"
        ? "质量降级"
        : "Public 队列为空";
  const detail =
    publishStatus === "hold_publish"
      ? `public write gate hold: ${reason}`
      : publishStatus === "degraded"
        ? `health degraded: ${reason}`
        : `hidden rows present: ${reason}`;
  return {
    title,
    detail,
    meta: `public ${publicCount} · hidden ${hiddenHold}`,
    tone: publishStatus === "hold_publish" ? "hold" : "degraded",
  };
}

function cleanHealthReason(value: string): string {
  return value.trim().replaceAll("_", " ");
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
