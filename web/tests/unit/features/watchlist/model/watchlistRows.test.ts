import { buildWatchlistRows } from "@features/watchlist";
import type { WatchlistHandleRowOverview } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("watchlist helpers", () => {
  it("keeps every server row and ranks unread then persisted activity", () => {
    const rows = buildWatchlistRows({
      accountUnreadCounts: { cz_binance: 1, traderpow: 3 },
      rows: [
        handleRow("toly", { lastSourceEventAtMs: 1_700_000_200_000, recentSignals: 4 }),
        handleRow("traderpow", { lastSourceEventAtMs: null }),
        handleRow("theunipcs", { lastSourceEventAtMs: 1_700_000_300_000, recentSignals: 8 }),
        handleRow("cz_binance", { lastSourceEventAtMs: 1_700_000_100_000, recentSources: 20 }),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["traderpow", "cz_binance", "theunipcs", "toly"]);
    expect(rows.map((row) => row.unreadCount)).toEqual([3, 1, 0, 0]);
    expect(rows.map((row) => row.recentSignalCount)).toEqual([0, 0, 8, 4]);
    expect(rows).toHaveLength(4);
  });

  it("exposes source stats and ranks active handles when unread counts tie", () => {
    const rows = buildWatchlistRows({
      accountUnreadCounts: {},
      rows: [
        handleRow("quiet", {
          lastSourceEventAtMs: 1_700_000_500_000,
          recentSignals: 0,
          recentSources: 1,
          totalSignals: 4,
        }),
        handleRow("signals", {
          lastSourceEventAtMs: 1_700_000_100_000,
          recentSignals: 6,
          recentSources: 8,
          stale: true,
          status: "ready",
          totalSignals: 80,
        }),
        handleRow("sources", {
          lastSourceEventAtMs: 1_700_000_400_000,
          recentSignals: 0,
          recentSources: 12,
          totalSignals: 12,
        }),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["signals", "sources", "quiet"]);
    expect(rows[0]).toMatchObject({
      activityScore: 68,
      lastSeenAtMs: 1_700_000_100_000,
      recentSignalCount: 6,
      recentSourceCount: 8,
      summaryIsStale: true,
      summaryStatus: "ready",
      totalSignalCount: 80,
    });
  });
});

function handleRow(
  handle: string,
  options: {
    lastSourceEventAtMs: number | null;
    recentSignals?: number;
    recentSources?: number;
    stale?: boolean;
    status?: "ready" | "not_ready";
    totalSignals?: number;
  },
): WatchlistHandleRowOverview {
  return {
    handle,
    last_source_event_at_ms: options.lastSourceEventAtMs,
    recent_source_event_count: options.recentSources ?? (options.lastSourceEventAtMs ? 1 : 0),
    recent_signal_event_count: options.recentSignals ?? 0,
    total_signal_event_count: options.totalSignals ?? 0,
    summary_status: options.status ?? "not_ready",
    summary_is_stale: options.stale ?? false,
  };
}
