import { MacroHeatmap } from "@features/macro/ui/charts/MacroHeatmap";
import { MacroNormalizedReturnChart } from "@features/macro/ui/charts/MacroNormalizedReturnChart";
import { MacroTimeSeriesChart } from "@features/macro/ui/charts/MacroTimeSeriesChart";
import { MacroYieldCurveChart } from "@features/macro/ui/charts/MacroYieldCurveChart";
import type { MacroModuleChart, MacroSeriesData } from "@lib/types";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const chartMocks = vi.hoisted(() => {
  const lineSeries = { setData: vi.fn() };
  const chartApi = {
    addSeries: vi.fn(() => lineSeries),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    resize: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  };
  return {
    chartApi,
    createChart: vi.fn(() => chartApi),
    lineSeries,
  };
});

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  LineSeries: "LineSeries",
  createChart: chartMocks.createChart,
}));

describe("Macro chart primitives", () => {
  beforeEach(() => {
    chartMocks.createChart.mockClear();
    chartMocks.chartApi.addSeries.mockClear();
    chartMocks.lineSeries.setData.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders an accessible time series chart from semantic backend payloads", () => {
    render(
      <MacroTimeSeriesChart
        chart={chartFixture()}
        seriesData={seriesFixture()}
        title="Equity trend"
      />,
    );

    const figure = screen.getByRole("figure", { name: "Equity trend" });
    expect(within(figure).getByText("S&P 500")).toBeInTheDocument();
    expect(within(figure).getByText("110")).toBeInTheDocument();
    expect(figure).not.toHaveTextContent("asset:spx");
    expect(chartMocks.createChart).toHaveBeenCalledTimes(1);
    expect(chartMocks.lineSeries.setData).toHaveBeenCalled();
  });

  it("keeps an empty chart state accessible without requiring canvas pixels", () => {
    render(<MacroTimeSeriesChart chart={{ id: "empty_chart", series: [] }} title="Empty chart" />);

    expect(screen.getByRole("figure", { name: "Empty chart" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Empty chart state" })).toHaveTextContent(
      "暂无可绘制序列",
    );
    expect(screen.getByRole("status", { name: "Empty chart state" })).not.toHaveTextContent(
      "chart_series_missing",
    );
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("renders insufficient-history state instead of drawing one-point series", () => {
    render(
      <MacroTimeSeriesChart
        chart={{
          id: "equity_proxy_performance",
          status: "insufficient_history",
          series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, point_count: 1 }],
        }}
        seriesData={{
          window: "60d",
          data_gaps: [
            { code: "insufficient_history:60d", label: "历史样本不足：无法计算 60 日变化" },
          ],
          series: {
            "asset:spx": {
              concept_key: "asset:spx",
              status: "insufficient_history",
              points: [{ observed_at: "2026-05-20", value: 110 }],
            },
          },
        }}
        title="History check"
      />,
    );

    const figure = screen.getByRole("figure", { name: "History check" });
    expect(within(figure).getByRole("status", { name: "History check state" })).toHaveTextContent(
      "历史样本不足",
    );
    expect(figure).not.toHaveTextContent("insufficient_history:60d");
    expect(figure).not.toHaveTextContent("insufficient_history");
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("uses backend chart min_points before drawing a sparse series", () => {
    render(
      <MacroTimeSeriesChart
        chart={{
          id: "strict_history_chart",
          min_points: 3,
          status_label: "需要至少 3 个观测点",
          series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, point_count: 2 }],
        }}
        seriesData={seriesFixture()}
        title="Strict history"
      />,
    );

    expect(screen.getByRole("status", { name: "Strict history state" })).toHaveTextContent(
      "需要至少 3 个观测点",
    );
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("renders normalized return values as backend-series display metadata", () => {
    render(
      <MacroNormalizedReturnChart
        chart={chartFixture("asset_proxy_performance")}
        seriesData={seriesFixture()}
        title="Normalized returns"
      />,
    );

    expect(screen.getByRole("figure", { name: "Normalized returns" })).toBeInTheDocument();
    expect(screen.getByText("10%")).toBeInTheDocument();
  });

  it("renders yield curve points in tenor order with raw backend values", () => {
    render(
      <MacroYieldCurveChart
        chart={{
          id: "yield_curve",
          series: [
            { concept_key: "rates:dgs10", latest: 4.2, unit: "percent" },
            { concept_key: "rates:dgs2", latest: 3.8, unit: "percent" },
            { concept_key: "rates:dgs30", latest: 4.7, unit: "percent" },
            { concept_key: "rates:dgs5", latest: 4.0, unit: "percent" },
          ],
        }}
        title="Yield curve"
      />,
    );

    const points = screen.getAllByTestId("macro-yield-curve-point");
    expect(points.map((point) => point.textContent)).toEqual([
      "2Y3.8%",
      "5Y4%",
      "10Y4.2%",
      "30Y4.7%",
    ]);
  });

  it("renders yield curve points from inline observations when latest is missing", () => {
    render(
      <MacroYieldCurveChart
        chart={{
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
        }}
        title="Yield curve"
      />,
    );

    const points = screen.getAllByTestId("macro-yield-curve-point");
    expect(points.map((point) => point.textContent)).toEqual(["2Y3.8%", "10Y4.2%"]);
  });

  it("renders localized chart empty states for yield curves and heatmaps", () => {
    const { rerender } = render(
      <MacroYieldCurveChart chart={{ id: "yield_curve", series: [] }} title="Yield curve" />,
    );

    expect(screen.getByRole("status", { name: "Yield curve state" })).toHaveTextContent(
      "暂无收益率曲线数据",
    );
    expect(screen.getByRole("status", { name: "Yield curve state" })).not.toHaveTextContent(
      "yield_curve_points_missing",
    );

    rerender(<MacroHeatmap caption="Asset correlation heatmap" rows={[]} />);

    expect(
      screen.getByRole("status", { name: "Asset correlation heatmap state" }),
    ).toHaveTextContent("暂无相关性矩阵数据");
    expect(
      screen.getByRole("status", { name: "Asset correlation heatmap state" }),
    ).not.toHaveTextContent("heatmap_rows_missing");
  });

  it("renders a heatmap as an accessible table with raw numeric labels", () => {
    render(
      <MacroHeatmap
        caption="Asset correlation heatmap"
        rows={[
          {
            concept_key: "asset:spy",
            label: "SPY",
            correlations: { "asset:spy": 1, "asset:qqq": 0.92 },
          },
          {
            concept_key: "asset:qqq",
            label: "QQQ",
            correlations: { "asset:spy": 0.92, "asset:qqq": 1 },
          },
        ]}
      />,
    );

    const table = screen.getByRole("table", { name: "Asset correlation heatmap" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["", "SPY", "QQQ"]);
    expect(within(table).getAllByText("0.92")).toHaveLength(2);
  });
});

function chartFixture(chartId = "equity_proxy_performance"): MacroModuleChart {
  return {
    id: chartId,
    series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" }],
  };
}

function seriesFixture(): MacroSeriesData {
  return {
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
}
