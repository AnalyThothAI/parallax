import {
  MACRO_MIN_CHART_POINTS,
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
      status: null,
    });
    expect(model.series[0]?.points).toEqual([
      { time: "2026-05-18", value: 100, sourceName: null, dataQuality: null },
      { time: "2026-05-20", value: 110, sourceName: null, dataQuality: null },
    ]);
    expect(model.series[0]?.points.length).toBeGreaterThanOrEqual(MACRO_MIN_CHART_POINTS);
    expect(model.series.map((series) => series.label)).not.toContain("rates:dgs10");
    expect(JSON.stringify(model.series[1])).not.toContain("insufficient_history");
  });

  it("drops unlabeled chart series instead of naming placeholders", () => {
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
    expect(JSON.stringify(model)).not.toContain("asset:spx");
  });

  it("does not expose chart series titles as series labels", () => {
    const model = buildMacroTimeSeriesModel(
      {
        id: "equity_proxy_performance",
        series: [
          { concept_key: "asset:spx", title: "Raw chart title", latest: 110, unit: "index" },
          { concept_key: "rates:dgs10", short_label: "10Y", latest: 4.1, unit: "percent" },
        ],
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
          "rates:dgs10": {
            concept_key: "rates:dgs10",
            points: [
              { observed_at: "2026-05-18", value: 4 },
              { observed_at: "2026-05-19", value: 4.1 },
            ],
          },
        },
      },
    );

    expect(model.series.map((series) => series.label)).toEqual(["10Y"]);
    expect(JSON.stringify(model)).not.toContain("Raw chart title");
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

  it("does not use hydrated series payload status or unit as chart display metadata", () => {
    const model = buildMacroTimeSeriesModel(
      {
        id: "equity_proxy_performance",
        series: [{ concept_key: "rates:dgs10", label: "10Y", latest: 4.1 }],
      },
      {
        window: "60d",
        data_gaps: [],
        series: {
          "rates:dgs10": {
            concept_key: "rates:dgs10",
            points: [
              { observed_at: "2026-05-18", value: 4 },
              { observed_at: "2026-05-19", value: 4.1 },
            ],
            status: "insufficient_history",
            status_label: "payload status must stay hidden",
            unit: "percent",
          },
        },
      },
    );

    expect(model.series[0]).toMatchObject({
      status: null,
      statusLabel: null,
      unit: null,
    });
    expect(JSON.stringify(model)).not.toContain("payload status must stay hidden");
    expect(JSON.stringify(model)).not.toContain("insufficient_history");
  });

  it("does not infer chart point counts from hydrated series payload length", () => {
    const model = buildMacroTimeSeriesModel(
      {
        id: "equity_proxy_performance",
        series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110 }],
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

    expect(model.series[0]?.pointCount).toBeNull();
    expect(JSON.stringify(model.series[0])).not.toContain('"pointCount":2');
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

  it("does not fall back to v2 inline chart points when hydrated series data is unavailable", () => {
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

    expect(model.series[0]?.points).toEqual([]);
    expect(JSON.stringify(model)).not.toContain("2026-05-18");
    expect(JSON.stringify(model)).not.toContain("2026-05-19");
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

  it("does not infer yield-curve latest values from v2 inline chart points", () => {
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
          latest: 3.8,
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

    expect(model.points.map((point) => point.conceptKey)).toEqual(["rates:dgs2"]);
    expect(model.points.map((point) => point.value)).toEqual([3.8]);
    expect(JSON.stringify(model)).not.toContain("rates:dgs10");
  });

  it("does not infer yield-curve latest values from legacy value fields", () => {
    const chart: MacroModuleChart = {
      id: "yield_curve",
      series: [
        {
          concept_key: "rates:dgs10",
          label: "10Y",
          unit: "percent",
          latest_value: 4.2,
        },
        {
          concept_key: "rates:dgs2",
          label: "2Y",
          unit: "percent",
          value: 3.8,
        },
        {
          concept_key: "rates:dgs5",
          label: "5Y",
          unit: "percent",
          latest: 4,
        },
      ],
    };

    const model = buildMacroYieldCurveModel(chart);

    expect(model.points.map((point) => point.conceptKey)).toEqual(["rates:dgs5"]);
    expect(model.points.map((point) => point.value)).toEqual([4]);
    expect(JSON.stringify(model)).not.toContain("rates:dgs10");
    expect(JSON.stringify(model)).not.toContain("rates:dgs2");
  });
});
