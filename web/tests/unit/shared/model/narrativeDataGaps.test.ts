import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import { describe, expect, it } from "vitest";

describe("narrativeDataGaps", () => {
  it("keeps semantic labeling pending distinct from insufficient samples", () => {
    expect(narrativeGapLabel({ reason: "semantic_labeling_pending" })).toBe("叙事分析中");
    expect(narrativeGapLabel({ reason: "low_source_volume" })).toBe("叙事样本不足");
  });
});
