import {
  liveRouteStateWith,
  parseLiveRouteState,
  serializeLiveRouteState,
} from "@features/live/state/liveRouteState";
import { describe, expect, it } from "vitest";

describe("liveRouteState", () => {
  it("uses product defaults when query params are omitted", () => {
    expect(parseLiveRouteState(new URLSearchParams())).toEqual({
      window: "1h",
      scope: "all",
    });
  });

  it("normalizes supported params and ignores retired handle noise", () => {
    expect(
      parseLiveRouteState(
        new URLSearchParams("window=4h&scope=matched&handles=@Toly, traderpow&sort=heat"),
      ),
    ).toEqual({
      window: "4h",
      scope: "matched",
    });
  });

  it("serializes only non-default params in stable order", () => {
    const search = serializeLiveRouteState({
      window: "24h",
      scope: "matched",
    });
    expect(search.toString()).toBe("window=24h&scope=matched");
  });

  it("normalizes patches before returning next state", () => {
    expect(
      liveRouteStateWith({ window: "1h", scope: "all" }, { window: "unsupported" as "1h" }),
    ).toEqual({ window: "1h", scope: "all" });
  });
});
