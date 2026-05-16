import type { WatchlistHandleRowOverview } from "@lib/types";

export type WatchlistRow = {
  handle: string;
  unreadCount: number;
  lastSeenAtMs: number | null;
};

type BuildWatchlistRowsInput = {
  accountUnreadCounts?: Record<string, number> | null;
  rows: WatchlistHandleRowOverview[];
};

export function buildWatchlistRows({
  accountUnreadCounts,
  rows,
}: BuildWatchlistRowsInput): WatchlistRow[] {
  const originalIndex = new Map(rows.map((row, index) => [row.handle, index]));
  return rows
    .map((row) => ({
      handle: row.handle,
      unreadCount: Number(accountUnreadCounts?.[row.handle] ?? 0),
      lastSeenAtMs: row.last_source_event_at_ms ?? null,
    }))
    .sort(
      (a, b) =>
        b.unreadCount - a.unreadCount ||
        Number(b.lastSeenAtMs ?? 0) - Number(a.lastSeenAtMs ?? 0) ||
        Number(originalIndex.get(a.handle) ?? 0) - Number(originalIndex.get(b.handle) ?? 0),
    );
}

export function emptyWatchlistHandleRow(handle: string): WatchlistHandleRowOverview {
  return {
    handle,
    last_source_event_at_ms: null,
    recent_source_event_count: 0,
    recent_signal_event_count: 0,
    total_signal_event_count: 0,
    summary_status: "not_ready",
    summary_is_stale: false,
  };
}
