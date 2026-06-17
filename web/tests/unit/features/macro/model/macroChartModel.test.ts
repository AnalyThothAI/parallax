import {
  MACRO_MIN_CHART_POINTS,
  buildMacroHeatmapMatrix,
  buildMacroNormalizedReturnModel,
  buildMacroTimeSeriesModel,
  buildMacroYieldCurveModel,
} from "@features/macro/model/macroChartModel";
import type { MacroModuleChart, MacroSeriesData } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroChartModel", () => {
  it("uses backend display labels and hides under-minimum series from drawable output", () => {
    const chart: MacroModuleChart = {
      id: "equity_proxy_performance",
      series: [
        { concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" },
        { concept_key: "rates:dgs10", short_label: "10Y", latest: 4.1, unit: "percent" },
      ],
    };
    const data: MacroSeriesData = {
      window: "60d",
      data_gaps: [{ code: "insufficient_history:60d", label: "历史样本不足：无法计算 60 日变化" }],
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
    expect(model.series[0]).toMatchObject({
      conceptKey: "asset:spx",
      label: "S&P 500",
      unit: "index",
    });
    expect(model.series[1]).toMatchObject({
      conceptKey: "rates:dgs10",
      label: "10Y",
      points: [],
      status: "insufficient_history",
    });
    expect(model.series[0]?.points).toEqual([
      { time: "2026-05-18", value: 100, sourceName: null, dataQuality: null },
      { time: "2026-05-20", value: 110, sourceName: null, dataQuality: null },
    ]);
    expect(model.series[0]?.points.length).toBeGreaterThanOrEqual(MACRO_MIN_CHART_POINTS);
    expect(model.series.map((series) => series.label)).not.toContain("rates:dgs10");
  });

  it("drops unlabeled chart series and heatmap rows instead of naming placeholders", () => {
    const model = buildMacroTimeSeriesModel(
      {
        id: "equity_proxy_performance",
        series: [{ concept_key: "asset:spx", latest: 110, unit: "index" }],
      },
      {
        window: "60d",
        data_gaps: [],
        series: {
          "asset:spx": {
            concept_key: "asset:spx",
            points: [
              { observed_at: "2026-05-18", value: 100 },
              { observed_at: "2026-05-19", value: 110 },
            ],
          },
        },
      },
    );

    expect(model.series).toEqual([]);

    const matrix = buildMacroHeatmapMatrix([
      {
        concept_key: "asset:spy",
        correlations: { "asset:spy": 1, "asset:qqq": 0.92 },
      },
      {
        concept_key: "asset:qqq",
        label: "QQQ",
        correlations: { "asset:spy": 0.92, "asset:qqq": 1 },
      },
    ]);

    expect(matrix.columns.map((column) => column.key)).toEqual(["asset:qqq"]);
    expect(matrix.rows.map((row) => row.label)).toEqual(["QQQ"]);
    expect(JSON.stringify(matrix)).not.toContain("未命名指标");
    expect(JSON.stringify(model)).not.toContain("asset:spx");
  });

  it("drops chart models with missing chart ids instead of assigning unknown ids", () => {
    const chart = {
      id: "",
      series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" }],
    } as MacroModuleChart;
    const data: MacroSeriesData = {
      window: "60d",
      data_gaps: [],
      series: {
        "asset:spx": {
          concept_key: "asset:spx",
          points: [
            { observed_at: "2026-05-18", value: 100 },
            { observed_at: "2026-05-19", value: 110 },
          ],
        },
      },
    };

    expect(buildMacroTimeSeriesModel(chart, data)).toMatchObject({
      chartId: "",
      series: [],
    });
    expect(buildMacroYieldCurveModel(chart)).toEqual({
      chartId: "",
      points: [],
    });
    expect(JSON.stringify(buildMacroTimeSeriesModel(chart, data))).not.toContain("unknown_chart");
  });

  it("does not manufacture unknown chart status when backend status metadata is absent", () => {
    const model = buildMacroTimeSeriesModel({
      id: "equity_proxy_performance",
      series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" }],
    });

    expect(model.status).toBeNull();
    expect(JSON.stringify(model)).not.toContain("unknown");
  });

  it("does not manufacture ok series status when backend series status is absent", () => {
    const model = buildMacroTimeSeriesModel(
      {
        id: "equity_proxy_performance",
        series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" }],
      },
      {
        window: "60d",
        data_gaps: [],
        series: {
          "asset:spx": {
            concept_key: "asset:spx",
            points: [
              { observed_at: "2026-05-18", value: 100 },
              { observed_at: "2026-05-19", value: 110 },
            ],
          },
        },
      },
    );

    expect(model.series[0]?.status).toBeNull();
    expect(JSON.stringify(model.series[0])).not.toContain('"ok"');
  });

  it("normalizes returns from the first numeric backend observation", () => {
    const chart: MacroModuleChart = {
      id: "asset_proxy_performance",
      series: [{ concept_key: "asset:spy", label: "SPY", latest: 104, unit: "usd" }],
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

  it("falls back to v2 inline chart points when hydrated series data is unavailable", () => {
    const model = buildMacroTimeSeriesModel({
      id: "equity_proxy_performance",
      series: [
        {
          concept_key: "asset:spx",
          label: "S&P 500",
          latest: 110,
          points: [
            { observed_at: "2026-05-18", value: 100 },
            { observed_at: "2026-05-19", value: 110 },
          ],
        },
      ],
    });

    expect(model.series[0]?.points.map((point) => point.value)).toEqual([100, 110]);
  });

  it("sorts yield curve points by semantic tenor concept keys", () => {
    const chart: MacroModuleChart = {
      id: "yield_curve",
      series: [
        { concept_key: "rates:dgs10", label: "10Y", latest: 4.2, unit: "percent" },
        { concept_key: "rates:dgs2", label: "2Y", latest: 3.8, unit: "percent" },
        { concept_key: "rates:10y2y", label: "10Y-2Y", latest: 0.4, unit: "percent" },
        { concept_key: "rates:dgs30", label: "30Y", latest: "4.7", unit: "percent" },
        { concept_key: "rates:dgs5", label: "5Y", latest: 4.0, unit: "percent" },
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

  it("drops yield curve points without backend labels instead of generating tenor labels", () => {
    const model = buildMacroYieldCurveModel({
      id: "yield_curve",
      series: [
        { concept_key: "rates:dgs10", latest: 4.2, unit: "percent" },
        { concept_key: "rates:dgs2", label: "2Y", latest: 3.8, unit: "percent" },
      ],
    });

    expect(model.points.map((point) => point.label)).toEqual(["2Y"]);
    expect(JSON.stringify(model)).not.toContain("10Y");
  });

  it("uses the latest inline point when a yield curve series omits latest", () => {
    const chart: MacroModuleChart = {
      id: "yield_curve",
      series: [
        {
          concept_key: "rates:dgs10",
          label: "10Y",
          unit: "percent",
          points: [
            { observed_at: "2026-05-19", value: 4.1 },
            { observed_at: "2026-05-20", value: "4.2" },
          ],
        },
        {
          concept_key: "rates:dgs2",
          label: "2Y",
          unit: "percent",
          points: [{ observed_at: "2026-05-20", value: 3.8 }],
        },
        {
          concept_key: "rates:10y2y",
          label: "10Y-2Y",
          unit: "percent",
          points: [{ observed_at: "2026-05-20", value: 0.4 }],
        },
      ],
    };

    const model = buildMacroYieldCurveModel(chart);

    expect(model.points.map((point) => point.conceptKey)).toEqual(["rates:dgs2", "rates:dgs10"]);
    expect(model.points.map((point) => point.value)).toEqual([3.8, 4.2]);
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
