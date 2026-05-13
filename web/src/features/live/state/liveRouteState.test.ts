import { describe, expect, it } from "vitest";

import { liveRouteStateWith, parseLiveRouteState, serializeLiveRouteState } from "./liveRouteState";

describe("liveRouteState", () => {
  it("uses product defaults when query params are omitted", () => {
    expect(parseLiveRouteState(new URLSearchParams())).toEqual({
      window: "1h",
      scope: "all",
      handles: "",
      sort: "opportunity",
    });
  });

  it("normalizes supported params and strips handle noise", () => {
    expect(
      parseLiveRouteState(
        new URLSearchParams("window=4h&scope=matched&handles=@Toly, traderpow&sort=heat"),
      ),
    ).toEqual({
      window: "4h",
      scope: "matched",
      handles: "toly,traderpow",
      sort: "heat",
    });
  });

  it("serializes only non-default params in stable order", () => {
    const search = serializeLiveRouteState({
      window: "24h",
      scope: "matched",
      handles: "toly",
      sort: "quality",
    });
    expect(search.toString()).toBe("window=24h&scope=matched&handles=toly&sort=quality");
  });

  it("normalizes patches before returning next state", () => {
    expect(
      liveRouteStateWith(
        { window: "1h", scope: "all", handles: "", sort: "opportunity" },
        { handles: " @Toly ", sort: "heat" },
      ),
    ).toEqual({ window: "1h", scope: "all", handles: "toly", sort: "heat" });
  });
});
