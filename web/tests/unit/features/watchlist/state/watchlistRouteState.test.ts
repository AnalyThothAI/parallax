import { parseWatchlistRouteState } from "@features/watchlist";
import { describe, expect, it } from "vitest";

describe("watchlist route state", () => {
  it("reads only the selected handle", () => {
    expect(parseWatchlistRouteState(new URLSearchParams("handle=marionawfal"), "toly")).toEqual({
      selectedHandle: "marionawfal",
    });
  });

  it("falls back to the configured handle", () => {
    expect(parseWatchlistRouteState(new URLSearchParams(), "toly")).toEqual({
      selectedHandle: "toly",
    });
  });
});
