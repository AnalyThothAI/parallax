import { buildRatesCorridorModel } from "@features/macro/model/macroRatesChartModel";
import { macroFedFundsModuleFixture, macroSeriesFixture } from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroRatesChartModel", () => {
  it("builds a corridor model from hydrated series and reports optional missing lines", () => {
    const model = buildRatesCorridorModel(
      macroFedFundsModuleFixture().primary_chart,
      macroSeriesFixture([
        "fed:target_lower",
        "fed:target_upper",
        "fed:effr",
        "fed:iorb",
        "liquidity:sofr",
      ]),
    );

    expect(model.lower?.label).toBe("目标下限");
    expect(model.upper?.label).toBe("目标上限");
    expect(model.lines.map((series) => series.label)).toEqual(["EFFR", "IORB", "SOFR"]);
    expect(model.missingLabels).toContain("SOFR 30D");
  });

  it("falls back to inline chart points and then latest snapshots", () => {
    const chart = macroFedFundsModuleFixture().primary_chart;
    const model = buildRatesCorridorModel(chart);

    expect(model.lower?.points.map((point) => point.value)).toEqual([4.25, 4.25]);
    expect(model.lines.find((series) => series.key === "iorb")?.points).toEqual([
      { time: "snapshot", value: 4.4 },
    ]);
  });
});
