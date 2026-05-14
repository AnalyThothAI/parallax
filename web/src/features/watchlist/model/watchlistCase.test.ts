import type { LivePayload } from "@lib/types";
import { describe, expect, it } from "vitest";

import { buildWatchlistAccountCases, normalizeWatchlistHandle } from "./watchlistCase";
import type { WatchlistRow } from "./watchlistRows";

describe("watchlist account cases", () => {
  it("derives account files from handles, unread state, recent evidence, tokens, and narratives", () => {
    const rows: WatchlistRow[] = [
      { handle: "TraderPow", lastSeenAtMs: 1_700_000_500_000, unreadCount: 3 },
      { handle: "toly", lastSeenAtMs: null, unreadCount: 0 },
    ];

    const cases = buildWatchlistAccountCases({
      liveItems: [
        liveEvent({
          cashtags: ["UPEG"],
          handle: "traderpow",
          hashtags: ["airdrop"],
          text: "$UPEG watched account evidence #airdrop",
        }),
        liveEvent({ cashtags: ["SOL"], handle: "toly", text: "$SOL founder account note" }),
      ],
      rows,
    });

    expect(cases.map((item) => item.handle)).toEqual(["traderpow", "toly"]);
    expect(cases[0].unreadCount).toBe(3);
    expect(cases[0].recentEvents[0].body).toBe("$UPEG watched account evidence #airdrop");
    expect(cases[0].recentEvents[0].meta).not.toBe("1700000500000");
    expect(cases[0].recentEvents[0].meta).toMatch(/^(\d+[smhd] ago|no timestamp)$/);
    expect(cases[0].tokenMentions).toEqual([{ count: 1, label: "$UPEG", query: "$UPEG" }]);
    expect(cases[0].narrativeClusters).toEqual([
      { count: 1, label: "#airdrop", query: "#airdrop" },
    ]);
    expect(cases[0].searchLinks[0]).toEqual({
      href: "/search?q=%40traderpow&window=24h&scope=all",
      label: "Search account",
    });
    expect(cases[1].emptyState).toBeNull();
  });

  it("normalizes selected handles for /watchlist?handle=", () => {
    expect(normalizeWatchlistHandle("@TraderPow ")).toBe("traderpow");
    expect(normalizeWatchlistHandle("")).toBeNull();
  });
});

function liveEvent({
  cashtags,
  handle,
  hashtags = [],
  text,
}: {
  cashtags: string[];
  handle: string;
  hashtags?: string[];
  text: string;
}): LivePayload {
  return {
    type: "event",
    event: {
      event_id: `${handle}-${cashtags.join("-")}`,
      author_handle: handle,
      canonical_url: `https://x.com/${handle}/status/1`,
      cashtags,
      hashtags,
      received_at_ms: 1_700_000_500_000,
      text_clean: text,
    },
    entities: cashtags.map((symbol) => ({
      entity_type: "symbol",
      normalized_value: symbol,
      received_at_ms: 1_700_000_500_000,
    })),
    alerts: [],
  };
}
