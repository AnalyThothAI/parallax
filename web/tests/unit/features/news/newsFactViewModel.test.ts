import { newsLifecycleTone, tokenLaneLabel } from "@features/news/model/newsFactViewModel";
import { describe, expect, it } from "vitest";

describe("news fact view model", () => {
  it.each([
    ["accepted", "is-ready"],
    ["processed", "is-ready"],
    ["rejected", "is-blocked"],
    ["attention", "is-waiting"],
  ])("maps lifecycle %s to %s", (status, tone) => {
    expect(newsLifecycleTone(status)).toBe(tone);
  });

  it("labels token identity lanes from persisted resolution facts", () => {
    expect(tokenLaneLabel({ lane: "resolved", resolution_status: "resolved" })).toBe("resolved");
    expect(tokenLaneLabel({ lane: "attention", resolution_status: null })).toBe("attention");
  });
});
