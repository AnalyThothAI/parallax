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

  it("renders corridor series only when the backend supplies display labels", () => {
    const chart = {
      ...macroFedFundsModuleFixture().primary_chart,
      series: [
        { concept_key: "fed:effr", label: "Desk EFFR", unit: "percent" },
        { concept_key: "fed:iorb", unit: "percent" },
      ],
    };

    const model = buildRatesCorridorModel(chart, macroSeriesFixture(["fed:effr", "fed:iorb"]));

    expect(model.lines.map((series) => ({ key: series.key, label: series.label }))).toEqual([
      { key: "effr", label: "Desk EFFR" },
    ]);
    expect(model.lines.map((series) => series.label)).not.toContain("EFFR");
    expect(model.lines.map((series) => series.label)).not.toContain("IORB");
    expect(model.missingLabels).toContain("IORB");
  });

  it("drops unknown corridor missing concept keys instead of exposing raw ids", () => {
    const chart = {
      ...macroFedFundsModuleFixture().primary_chart,
      missing_concept_keys: ["fed:sofr_30d", "fed:not_mapped"],
    };

    const model = buildRatesCorridorModel(chart);

    expect(model.missingLabels).toContain("SOFR 30D");
    expect(model.missingLabels).not.toContain("fed:not_mapped");
    expect(model.missingLabels.join("\n")).not.toContain("not_mapped");
  });

  it("does not use v2 inline chart points as corridor data", () => {
    const chart = macroFedFundsModuleFixture().primary_chart;
    const model = buildRatesCorridorModel(chart);

    expect(model.lower).toBeNull();
    expect(model.upper).toBeNull();
    expect(model.lines).toEqual([]);
    expect(model.missingLabels).toContain("目标下限");
    expect(model.missingLabels).toContain("目标上限");
    expect(model.missingLabels).toContain("EFFR");
    expect(model.missingLabels).toContain("IORB");
    expect(JSON.stringify(model)).not.toContain("2026-05-20");
    expect(JSON.stringify(model)).not.toContain("snapshot");
  });

  it("does not use hydrated payload metadata as corridor display fallback", () => {
    const chart = {
      ...macroFedFundsModuleFixture().primary_chart,
      series: [{ concept_key: "fed:target_lower", label: "目标下限" }],
    };
    const model = buildRatesCorridorModel(chart, {
      window: "60d",
      data_gaps: [],
      series: {
        "fed:target_lower": {
          concept_key: "fed:target_lower",
          status: "ok",
          unit: "basis-points-from-payload",
          latest_value: 99,
          points: [{ observed_at: "2026-06-10", value: 4.5, source_name: "fixture" }],
        },
      },
    });

    expect(model.lower?.latest).toBe(4.5);
    expect(model.lower?.unit).toBeNull();
    expect(JSON.stringify(model)).not.toContain("basis-points-from-payload");
    expect(JSON.stringify(model)).not.toContain("99");
  });
});
