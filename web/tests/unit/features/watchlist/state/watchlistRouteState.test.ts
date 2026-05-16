import { parseWatchlistRouteState, serializeWatchlistTimelineScope } from "@features/watchlist";
import { describe, expect, it } from "vitest";

describe("watchlist route state", () => {
  it("uses timeline_scope as the canonical watchlist scope key", () => {
    expect(
      parseWatchlistRouteState(
        new URLSearchParams("handle=marionawfal&timeline_scope=all"),
        "toly",
      ),
    ).toEqual({
      selectedHandle: "marionawfal",
      timelineScope: "all",
    });
  });

  it("ignores the live radar scope key instead of translating it", () => {
    expect(
      parseWatchlistRouteState(new URLSearchParams("handle=marionawfal&scope=all"), "toly")
        .timelineScope,
    ).toBe("signal");
  });

  it("preserves the selected handle and removes the live radar scope key", () => {
    const next = serializeWatchlistTimelineScope(
      new URLSearchParams("handle=marionawfal&scope=matched"),
      "all",
      "marionawfal",
    );

    expect(next.toString()).toBe("handle=marionawfal&timeline_scope=all");
  });
});
