import {
  parseSignalLabRouteState,
  serializeSignalLabRouteState,
  signalLabRouteSearch,
} from "@features/signal-lab/state/signalLabRouteState";
import { describe, expect, it } from "vitest";

describe("signalLabRouteState", () => {
  it("uses product defaults when query params are omitted", () => {
    expect(parseSignalLabRouteState(new URLSearchParams())).toEqual({
      window: "4h",
      scope: "all",
      status: "all",
      handle: "",
      q: "",
    });
  });

  it("normalizes supported params and strips @ from handles", () => {
    expect(
      parseSignalLabRouteState(
        new URLSearchParams("window=1h&scope=matched&status=token_watch&handle=@Toly&q=SOL"),
      ),
    ).toEqual({
      window: "1h",
      scope: "matched",
      status: "token_watch",
      handle: "toly",
      q: "SOL",
    });
  });

  it("falls back to defaults for invalid enum params", () => {
    expect(
      parseSignalLabRouteState(
        new URLSearchParams("window=5m&scope=private&status=moon&handle=  @TraderPow  "),
      ),
    ).toEqual({
      window: "4h",
      scope: "all",
      status: "all",
      handle: "traderpow",
      q: "",
    });
  });

  it("omits defaults when serializing to URL search params", () => {
    expect(
      serializeSignalLabRouteState({
        window: "4h",
        scope: "all",
        status: "all",
        handle: "",
        q: "",
      }).toString(),
    ).toBe("");
  });

  it("serializes non-default params in a stable order", () => {
    expect(
      signalLabRouteSearch({
        window: "1h",
        scope: "matched",
        status: "trade_candidate",
        handle: "toly",
        q: "SOL",
      }),
    ).toBe("?window=1h&scope=matched&status=trade_candidate&handle=toly&q=SOL");
  });

  it("normalizes removed pulse windows to the 4h default", () => {
    expect(parseSignalLabRouteState(new URLSearchParams("window=24h")).window).toBe("4h");
    expect(
      serializeSignalLabRouteState({
        window: "5m",
        scope: "all",
        status: "all",
        handle: "",
        q: "",
      }).toString(),
    ).toBe("");
  });
});
