import { buildWatchlistRows } from "@features/watchlist";
import type { WatchlistHandleRowOverview } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("watchlist helpers", () => {
  it("keeps every server row and ranks unread then persisted activity", () => {
    const rows = buildWatchlistRows({
      accountUnreadCounts: { cz_binance: 1, traderpow: 3 },
      rows: [
        handleRow("toly", { lastSourceEventAtMs: 1_700_000_200_000 }),
        handleRow("traderpow", { lastSourceEventAtMs: null }),
        handleRow("theunipcs", { lastSourceEventAtMs: 1_700_000_300_000 }),
        handleRow("cz_binance", { lastSourceEventAtMs: 1_700_000_100_000, recentSources: 20 }),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["traderpow", "cz_binance", "theunipcs", "toly"]);
    expect(rows.map((row) => row.unreadCount)).toEqual([3, 1, 0, 0]);
    expect(rows).toHaveLength(4);
  });

  it("exposes source stats and ranks active handles when unread counts tie", () => {
    const rows = buildWatchlistRows({
      accountUnreadCounts: {},
      rows: [
        handleRow("quiet", {
          lastSourceEventAtMs: 1_700_000_500_000,
          recentSources: 1,
        }),
        handleRow("signals", {
          lastSourceEventAtMs: 1_700_000_100_000,
          recentSources: 8,
        }),
        handleRow("sources", {
          lastSourceEventAtMs: 1_700_000_400_000,
          recentSources: 12,
        }),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["sources", "signals", "quiet"]);
    expect(rows[0]).toMatchObject({
      activityScore: 12,
      lastSeenAtMs: 1_700_000_400_000,
      recentSourceCount: 12,
    });
  });
});

function handleRow(
  handle: string,
  options: {
    lastSourceEventAtMs: number | null;
    recentSources?: number;
  },
): WatchlistHandleRowOverview {
  return {
    handle,
    last_source_event_at_ms: options.lastSourceEventAtMs,
    recent_source_event_count: options.recentSources ?? (options.lastSourceEventAtMs ? 1 : 0),
  };
}
