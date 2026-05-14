import { describe, expect, it } from "vitest";

import { liveRouteStateWith, parseLiveRouteState, serializeLiveRouteState } from "./liveRouteState";

describe("liveRouteState", () => {
  it("uses product defaults when query params are omitted", () => {
    expect(parseLiveRouteState(new URLSearchParams())).toEqual({
      window: "1h",
      scope: "all",
      handles: "",
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
    });
  });

  it("serializes only non-default params in stable order", () => {
    const search = serializeLiveRouteState({
      window: "24h",
      scope: "matched",
      handles: "toly",
    });
    expect(search.toString()).toBe("window=24h&scope=matched&handles=toly");
  });

  it("normalizes patches before returning next state", () => {
    expect(
      liveRouteStateWith({ window: "1h", scope: "all", handles: "" }, { handles: " @Toly " }),
    ).toEqual({ window: "1h", scope: "all", handles: "toly" });
  });
});
