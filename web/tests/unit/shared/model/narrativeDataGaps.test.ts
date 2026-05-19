import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import { describe, expect, it } from "vitest";

describe("narrativeDataGaps", () => {
  it("keeps semantic labeling pending distinct from insufficient samples", () => {
    expect(narrativeGapLabel({ reason: "semantic_labeling_pending" })).toBe(
      "semantic labeling pending",
    );
  });
});
