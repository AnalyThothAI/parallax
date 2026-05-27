import type { EquityEventCalendarRow, EquityEventRow } from "./equityEventTypes";

export type EquityEventFeedModel = {
  rows: EquityEventRow[];
  summary: {
    total: number;
    p0: number;
    ready: number;
    pending: number;
    drivers: number;
  };
  emptyTitle: string;
};

export type EquityEventFeedModelOptions = {
  ordering?: "backend" | "priority";
};

export const buildEquityEventFeedModel = (
  rows: EquityEventRow[],
  options: EquityEventFeedModelOptions = {},
): EquityEventFeedModel => {
  const sortedRows = options.ordering === "priority" ? sortEquityEventRows(rows) : [...rows];
  return {
    rows: sortedRows,
    summary: {
      total: sortedRows.length,
      p0: sortedRows.filter((row) => row.priority === "P0").length,
      ready: sortedRows.filter((row) => row.brief.status === "ready").length,
      pending: sortedRows.filter((row) => row.brief.status === "pending").length,
      drivers: sortedRows.filter((row) => row.brief.decision_class === "driver").length,
    },
    emptyTitle: "No equity event rows",
  };
};

export const sortEquityEventRows = (rows: EquityEventRow[]): EquityEventRow[] =>
  [...rows].sort((left, right) => {
    const priorityDelta =
      equityEventPriorityRank(left.priority) - equityEventPriorityRank(right.priority);
    if (priorityDelta !== 0) return priorityDelta;
    return (right.latest_event_at_ms ?? 0) - (left.latest_event_at_ms ?? 0);
  });

export const sortEquityCalendarRows = (rows: EquityEventCalendarRow[]): EquityEventCalendarRow[] =>
  [...rows].sort((left, right) => {
    const timeDelta = (left.expected_at_ms ?? 0) - (right.expected_at_ms ?? 0);
    if (timeDelta !== 0) return timeDelta;
    return left.ticker.localeCompare(right.ticker);
  });

export const equityEventPriorityRank = (priority?: string | null): number => {
  const ranks: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3 };
  return ranks[priority ?? ""] ?? 9;
};

export const equityEventBriefStatusLabel = (status?: string | null): string => {
  const labels: Record<string, string> = {
    disabled: "brief disabled",
    failed_retryable: "brief retryable",
    failed_terminal: "brief failed",
    historical_unscheduled: "historical backlog",
    insufficient: "insufficient brief",
    in_progress: "brief running",
    pending: "pending brief",
    pending_due: "brief due",
    ready: "brief ready",
    stale: "brief stale",
  };
  return labels[status ?? ""] ?? status ?? "pending brief";
};

export const equityCalendarStatusLabel = (status?: string | null): string => {
  const labels: Record<string, string> = {
    expected: "expected",
    matched: "matched",
    missed: "missed",
  };
  return labels[status ?? ""] ?? status ?? "expected";
};

export const equityEventTypeLabel = (eventType?: string | null): string =>
  (eventType ?? "event").replaceAll("_", " ");

export const equityEventTimestampLabel = (timestamp: number | null): string => {
  if (!timestamp) return "time unknown";
  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(new Date(timestamp));
};

export const equityEventSourceLabel = (sourceRole?: string | null): string =>
  (sourceRole ?? "source").replaceAll("_", " ");
