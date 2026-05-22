import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import { describe, expect, it } from "vitest";

describe("narrativeDataGaps", () => {
  it("keeps semantic labeling pending distinct from insufficient samples", () => {
    expect(narrativeGapLabel({ reason: "semantic_labeling_pending" })).toBe("叙事分析中");
    expect(narrativeGapLabel({ reason: "low_source_volume" })).toBe("叙事样本不足");
  });

  it("labels hard-cut currentness reasons", () => {
    expect(narrativeGapLabel({ reason: "no_ready_digest" })).toBe("叙事待生成");
    expect(narrativeGapLabel({ reason: "no_reusable_1h_digest" })).toBe("1h 叙事待生成");
    expect(narrativeGapLabel({ reason: "target_current_1h_narrative" })).toBe("1h 叙事已读");
    expect(narrativeGapLabel({ reason: "thresholds_met_partial_semantic_tail" })).toBe(
      "1h 叙事已读",
    );
    expect(narrativeGapLabel({ reason: "digest_updating" })).toBe("叙事更新中");
    expect(narrativeGapLabel({ reason: "material_delta_due" })).toBe("叙事刷新排队中");
    expect(narrativeGapLabel({ reason: "unsupported_window" })).toBe("5m 实时信号");
    expect(narrativeGapLabel({ reason: "narrative_not_supported_for_window" })).toBe(
      "5m 实时信号",
    );
    expect(narrativeGapLabel({ reason: "out_of_frontier" })).toBe("不在当前雷达前沿");
    expect(narrativeGapLabel({ reason: "not_in_current_frontier" })).toBe("不在当前雷达前沿");
  });

  it("does not keep digest_stale as a primary hard-cut label", () => {
    expect(narrativeGapLabel({ reason: "digest_stale" })).toBe("digest stale");
  });
});
