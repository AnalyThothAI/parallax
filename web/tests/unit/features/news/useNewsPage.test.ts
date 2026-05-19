import { newsLifecycleLabel, newsTokenLaneLabel } from "@shared/model/newsIntel";
import { describe, expect, it } from "vitest";

describe("newsIntel model", () => {
  it("labels attention lifecycle explicitly", () => {
    expect(newsLifecycleLabel("attention")).toBe("Attention");
  });

  it("labels unknown token lane without pretending it is resolved", () => {
    expect(
      newsTokenLaneLabel({
        lane: "attention",
        resolution_status: "unknown_attention",
        symbol: "NEWX",
      }),
    ).toBe("NEWX · attention");
  });
});
