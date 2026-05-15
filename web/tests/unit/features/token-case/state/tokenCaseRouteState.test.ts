import {
  parseTokenCaseRouteState,
  serializeTokenCaseRouteState,
  tokenCaseScopeToApiScope,
} from "@features/token-case/state/tokenCaseRouteState";
import { describe, expect, it } from "vitest";

describe("tokenCaseRouteState", () => {
  it("uses defaults when params are omitted", () => {
    expect(parseTokenCaseRouteState(new URLSearchParams())).toEqual({
      window: "1h",
      scope: "all",
      postSort: "recent",
    });
  });

  it("accepts supported window, watched scope, and sort params", () => {
    expect(
      parseTokenCaseRouteState(new URLSearchParams("window=24h&scope=watched&postSort=catalyst")),
    ).toEqual({
      window: "24h",
      scope: "watched",
      postSort: "catalyst",
    });
  });

  it("parses inbound matched scope as watched", () => {
    expect(parseTokenCaseRouteState(new URLSearchParams("scope=matched")).scope).toBe("watched");
  });

  it("falls back to defaults for invalid enum params", () => {
    expect(
      parseTokenCaseRouteState(new URLSearchParams("window=7d&scope=private&postSort=quality")),
    ).toEqual({
      window: "1h",
      scope: "all",
      postSort: "recent",
    });
  });

  it("omits defaults when serializing", () => {
    expect(
      serializeTokenCaseRouteState({
        window: "1h",
        scope: "all",
        postSort: "recent",
      }).toString(),
    ).toBe("");
  });

  it("serializes public watched scope in stable order", () => {
    expect(
      serializeTokenCaseRouteState({
        window: "24h",
        scope: "watched",
        postSort: "recent",
      }).toString(),
    ).toBe("window=24h&scope=watched");
  });

  it("maps public scope to the token-case API scope", () => {
    expect(tokenCaseScopeToApiScope("all")).toBe("all");
    expect(tokenCaseScopeToApiScope("watched")).toBe("watched");
  });
});
