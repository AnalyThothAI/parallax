import type { WatchlistHandleRowOverview } from "@lib/types";

export type WatchlistRow = {
  activityScore: number;
  handle: string;
  lastSeenAtMs: number | null;
  recentSignalCount: number;
  recentSourceCount: number;
  summaryIsStale: boolean;
  summaryStatus: WatchlistHandleRowOverview["summary_status"];
  totalSignalCount: number;
  unreadCount: number;
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
      activityScore:
        Number(row.recent_signal_event_count ?? 0) * 10 +
        Number(row.recent_source_event_count ?? 0),
      handle: row.handle,
      lastSeenAtMs: row.last_source_event_at_ms ?? null,
      recentSignalCount: Number(row.recent_signal_event_count ?? 0),
      recentSourceCount: Number(row.recent_source_event_count ?? 0),
      summaryIsStale: Boolean(row.summary_is_stale),
      summaryStatus: row.summary_status,
      totalSignalCount: Number(row.total_signal_event_count ?? 0),
      unreadCount: Number(accountUnreadCounts?.[row.handle] ?? 0),
    }))
    .sort(
      (a, b) =>
        b.unreadCount - a.unreadCount ||
        b.recentSignalCount - a.recentSignalCount ||
        b.recentSourceCount - a.recentSourceCount ||
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
