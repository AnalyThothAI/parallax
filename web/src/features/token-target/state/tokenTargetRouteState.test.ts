import { describe, expect, it } from "vitest";

import {
  parseTokenTargetRouteState,
  serializeTokenTargetRouteState,
} from "./tokenTargetRouteState";

describe("tokenTargetRouteState", () => {
  it("uses route defaults when params are omitted", () => {
    expect(parseTokenTargetRouteState(new URLSearchParams())).toEqual({
      window: "1h",
      scope: "all",
      tab: "timeline",
      postRange: "current_window",
      postSort: "recent",
    });
  });

  it("accepts supported window, scope, tab, range, and sort params", () => {
    expect(
      parseTokenTargetRouteState(
        new URLSearchParams(
          "window=24h&scope=matched&tab=posts&postRange=since_ignition&postSort=catalyst",
        ),
      ),
    ).toEqual({
      window: "24h",
      scope: "matched",
      tab: "posts",
      postRange: "since_ignition",
      postSort: "catalyst",
    });
  });

  it("falls back to defaults for invalid enum params", () => {
    expect(
      parseTokenTargetRouteState(
        new URLSearchParams("window=7d&scope=private&tab=nope&postRange=bad&postSort=bad"),
      ),
    ).toEqual({
      window: "1h",
      scope: "all",
      tab: "timeline",
      postRange: "current_window",
      postSort: "recent",
    });
  });

  it("omits defaults when serializing", () => {
    expect(
      serializeTokenTargetRouteState({
        window: "1h",
        scope: "all",
        tab: "timeline",
        postRange: "current_window",
        postSort: "recent",
      }).toString(),
    ).toBe("");
  });

  it("serializes non-default params in stable order", () => {
    expect(
      serializeTokenTargetRouteState({
        window: "4h",
        scope: "matched",
        tab: "accounts",
        postRange: "all_history",
        postSort: "quality",
      }).toString(),
    ).toBe("window=4h&scope=matched&tab=accounts&postRange=all_history&postSort=quality");
  });
});
