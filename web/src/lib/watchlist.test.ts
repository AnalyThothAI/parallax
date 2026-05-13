import type { LivePayload } from "@lib/types";
import { describe, expect, it } from "vitest";


import { buildWatchlistRows } from "./watchlist";

describe("watchlist helpers", () => {
  it("keeps every configured handle and ranks unread then latest activity", () => {
    const rows = buildWatchlistRows({
      handles: ["toly", "traderpow", "theunipcs", "cz_binance"],
      accountUnreadCounts: { cz_binance: 1, traderpow: 3 },
      liveItems: [
        liveEvent("theunipcs", 1_700_000_300_000),
        liveEvent("toly", 1_700_000_200_000),
        liveEvent("cz_binance", 1_700_000_100_000),
      ],
    });

    expect(rows.map((row) => row.handle)).toEqual(["traderpow", "cz_binance", "theunipcs", "toly"]);
    expect(rows.map((row) => row.unreadCount)).toEqual([3, 1, 0, 0]);
    expect(rows).toHaveLength(4);
  });
});

function liveEvent(handle: string, receivedAtMs: number): LivePayload {
  return {
    type: "event",
    event: {
      event_id: `${handle}-${receivedAtMs}`,
      author_handle: handle,
      received_at_ms: receivedAtMs,
    },
    entities: [],
    alerts: [],
  };
}
