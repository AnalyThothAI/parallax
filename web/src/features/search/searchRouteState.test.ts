import { describe, expect, it } from "vitest";

import { parseSearchRouteState, serializeSearchRouteState } from "./searchRouteState";

describe("searchRouteState", () => {
  it("defaults to 24h/all and preserves q", () => {
    expect(parseSearchRouteState(new URLSearchParams("q=%24RKC"))).toEqual({
      q: "$RKC",
      window: "24h",
      scope: "all",
    });
  });

  it("drops unsupported window and scope values", () => {
    expect(parseSearchRouteState(new URLSearchParams("q=mining&window=bad&scope=bad"))).toEqual({
      q: "mining",
      window: "24h",
      scope: "all",
    });
  });

  it("serializes stable shareable URLs", () => {
    expect(serializeSearchRouteState({ q: "挖矿", window: "24h", scope: "all" }).toString()).toBe(
      "q=%E6%8C%96%E7%9F%BF&window=24h&scope=all",
    );
  });
});
