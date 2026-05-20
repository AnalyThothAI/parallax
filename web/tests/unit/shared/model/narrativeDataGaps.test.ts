import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import { describe, expect, it } from "vitest";

describe("narrativeDataGaps", () => {
  it("keeps semantic labeling pending distinct from insufficient samples", () => {
    expect(narrativeGapLabel({ reason: "semantic_labeling_pending" })).toBe("叙事分析中");
    expect(narrativeGapLabel({ reason: "low_source_volume" })).toBe("叙事样本不足");
  });

  it("labels hard-cut digest and budget reasons", () => {
    expect(narrativeGapLabel({ reason: "digest_stale" })).toBe("叙事已过期");
    expect(narrativeGapLabel({ reason: "not_in_current_frontier" })).toBe("不在当前雷达前沿");
    expect(narrativeGapLabel({ reason: "llm_cycle_budget_exhausted" })).toBe("叙事刷新排队中");
    expect(narrativeGapLabel({ reason: "llm_failure_budget_exhausted" })).toBe("叙事服务退避中");
  });
});
