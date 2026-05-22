import {
  buildMacroHeatmapMatrix,
  buildMacroNormalizedReturnModel,
  buildMacroTimeSeriesModel,
  buildMacroYieldCurveModel,
} from "@features/macro/model/macroChartModel";
import type { MacroModuleChart, MacroSeriesData } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroChartModel", () => {
  it("extracts chart series from backend concept keys without inventing provider keys", () => {
    const chart: MacroModuleChart = {
      chart_id: "equity_proxy_performance",
      series: [
        { concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" },
        { concept_key: "rates:dgs10", latest: 4.1, unit: "percent" },
      ],
    };
    const data: MacroSeriesData = {
      window: "60d",
      data_gaps: [],
      series: {
        "asset:spx": {
          concept_key: "asset:spx",
          points: [
            { observed_at: "2026-05-20", value: 110 },
            { observed_at: "2026-05-18", value: "100" },
            { observed_at: "2026-05-19", value: "bad" },
          ],
        },
        "rates:dgs10": {
          concept_key: "rates:dgs10",
          points: [{ observed_at: "2026-05-20", value: "4.1" }],
        },
        "fred:DGS10": {
          concept_key: "fred:DGS10",
          points: [{ observed_at: "2026-05-20", value: 4.1 }],
        },
      },
    };

    const model = buildMacroTimeSeriesModel(chart, data);

    expect(model.series.map((series) => series.conceptKey)).toEqual(["asset:spx", "rates:dgs10"]);
    expect(model.series[0]).toMatchObject({ conceptKey: "asset:spx", label: "S&P 500", unit: "index" });
    expect(model.series[0]?.points).toEqual([
      { time: "2026-05-18", value: 100, sourceName: null, dataQuality: null },
      { time: "2026-05-20", value: 110, sourceName: null, dataQuality: null },
    ]);
  });

  it("normalizes returns from the first numeric backend observation", () => {
    const chart: MacroModuleChart = {
      chart_id: "asset_proxy_performance",
      series: [{ concept_key: "asset:spy", latest: 104, unit: "usd" }],
    };
    const data: MacroSeriesData = {
      window: "60d",
      data_gaps: [],
      series: {
        "asset:spy": {
          concept_key: "asset:spy",
          points: [
            { observed_at: "2026-05-18", value: 100 },
            { observed_at: "2026-05-19", value: 110 },
            { observed_at: "2026-05-20", value: 104 },
          ],
        },
      },
    };

    const model = buildMacroNormalizedReturnModel(chart, data);

    expect(model.series[0]?.unit).toBe("return_percent");
    expect(model.series[0]?.points.map((point) => point.value)).toEqual([0, 10, 4]);
  });

  it("sorts yield curve points by semantic tenor concept keys", () => {
    const chart: MacroModuleChart = {
      chart_id: "yield_curve",
      series: [
        { concept_key: "rates:dgs10", latest: 4.2, unit: "percent" },
        { concept_key: "rates:dgs2", latest: 3.8, unit: "percent" },
        { concept_key: "rates:10y2y", latest: 0.4, unit: "percent" },
        { concept_key: "rates:dgs30", latest: "4.7", unit: "percent" },
        { concept_key: "rates:dgs5", latest: 4.0, unit: "percent" },
      ],
    };

    const model = buildMacroYieldCurveModel(chart);

    expect(model.points.map((point) => point.conceptKey)).toEqual([
      "rates:dgs2",
      "rates:dgs5",
      "rates:dgs10",
      "rates:dgs30",
    ]);
    expect(model.points.map((point) => point.tenorYears)).toEqual([2, 5, 10, 30]);
  });

  it("coerces heatmap matrix rows to raw numeric labels using row keys as columns", () => {
    const matrix = buildMacroHeatmapMatrix([
      {
        concept_key: "asset:spy",
        label: "SPY",
        correlations: { "asset:spy": 1, "asset:qqq": "0.92", "fred:DGS10": 0.1 },
      },
      {
        concept_key: "asset:qqq",
        label: "QQQ",
        correlations: { "asset:spy": 0.92, "asset:qqq": 1, "asset:tlt": null },
      },
    ]);

    expect(matrix.columns.map((column) => column.key)).toEqual(["asset:spy", "asset:qqq"]);
    expect(matrix.rows.map((row) => row.label)).toEqual(["SPY", "QQQ"]);
    expect(matrix.rows[0]?.cells.map((cell) => cell.rawValue)).toEqual([1, 0.92]);
    expect(matrix.rows[0]?.cells.map((cell) => cell.label)).toEqual(["1", "0.92"]);
  });
});
