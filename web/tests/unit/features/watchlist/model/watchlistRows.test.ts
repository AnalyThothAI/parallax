import { buildWatchlistRows } from "@features/watchlist";
import type { WatchlistHandleRowOverview } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("watchlist helpers", () => {
  it("keeps every server row and ranks unread then persisted activity", () => {
    const rows = buildWatchlistRows({
      accountUnreadCounts: { cz_binance: 1, traderpow: 3 },
      rows: [
        handleRow("toly", 1_700_000_200_000),
        handleRow("traderpow", null),
        handleRow("theunipcs", 1_700_000_300_000),
        handleRow("cz_binance", 1_700_000_100_000),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["traderpow", "cz_binance", "theunipcs", "toly"]);
    expect(rows.map((row) => row.unreadCount)).toEqual([3, 1, 0, 0]);
    expect(rows).toHaveLength(4);
  });
});

function handleRow(handle: string, lastSourceEventAtMs: number | null): WatchlistHandleRowOverview {
  return {
    handle,
    last_source_event_at_ms: lastSourceEventAtMs,
    recent_source_event_count: lastSourceEventAtMs ? 1 : 0,
    recent_signal_event_count: 0,
    total_signal_event_count: 0,
    summary_status: "not_ready",
    summary_is_stale: false,
  };
}
