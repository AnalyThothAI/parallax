import type { MacroAssetCorrelationData } from "@lib/types";
import { describe, expect, it } from "vitest";

import {
  assetLabel,
  assetTitleByKey,
  correlationGapLabel,
  correlationTone,
  matrixCorrelationLabel,
  signedCorrelationLabel,
  sourceLabel,
  strongestCorrelationPairs,
} from "@features/macro";

describe("macroCorrelationModel", () => {
  it("sorts available correlation pairs by direction and caps the result", () => {
    const data = correlationFixture({
      pairs: [
        pair("asset:spy", "asset:qqq", 0.4),
        pair("asset:spy", "asset:tlt", -0.6),
        pair("asset:qqq", "crypto:eth", 0.9),
        pair("asset:tlt", "crypto:eth", -0.2),
        { ...pair("asset:tlt", "asset:qqq", 0.99), available: false },
      ],
    });

    expect(strongestCorrelationPairs(data, "positive").map((item) => item.correlation)).toEqual([
      0.9,
      0.4,
    ]);
    expect(strongestCorrelationPairs(data, "negative").map((item) => item.correlation)).toEqual([
      -0.6,
      -0.2,
    ]);
  });

  it("formats correlation labels, asset labels, source labels, gaps, and tone", () => {
    const data = correlationFixture();
    const titleByKey = assetTitleByKey(data);

    expect(titleByKey).toEqual({
      "asset:qqq": "QQQ",
      "asset:spy": "SPY",
    });
    expect(assetLabel("asset:spy", titleByKey)).toBe("SPY");
    expect(assetLabel("missing", titleByKey)).toBe("资产");
    expect(sourceLabel("yahoo")).toBe("Yahoo");
    expect(sourceLabel("internal:asset_proxy")).toBe("数据源");
    expect(sourceLabel("Custom Feed")).toBe("Custom Feed");
    expect(matrixCorrelationLabel(0.923)).toBe("0.92");
    expect(matrixCorrelationLabel(null)).toBe("-");
    expect(signedCorrelationLabel(0.923)).toBe("+0.92");
    expect(signedCorrelationLabel(-0.4)).toBe("-0.40");
    expect(correlationTone(0.55)).toBe("constructive");
    expect(correlationTone(-0.35)).toBe("stress");
    expect(correlationTone(null)).toBe("gap");
    expect(
      correlationGapLabel(
        { code: "insufficient_overlap", left: "asset:spy", right: "asset:qqq", sample_size: 2 },
        titleByKey,
      ),
    ).toBe("重叠样本不足：SPY / QQQ");
  });
});

function pair(left: string, right: string, correlation: number) {
  return {
    available: true,
    correlation,
    end_date: "2026-05-20",
    left,
    reason: null,
    right,
    sample_size: 60,
    start_date: "2026-02-20",
  };
}

function correlationFixture(
  overrides: Partial<MacroAssetCorrelationData> = {},
): MacroAssetCorrelationData {
  return {
    window: "60d",
    asof_date: "2026-05-20",
    assets: [
      {
        concept_key: "asset:spy",
        title: "SPY",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
      {
        concept_key: "asset:qqq",
        title: "QQQ",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
    ],
    matrix: [],
    pairs: [],
    data_gaps: [],
    ...overrides,
  };
}
