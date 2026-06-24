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

  it("returns no time-series chrome when the chart has no drawable series", () => {
    const { container } = render(
      <MacroTimeSeriesChart chart={{ id: "empty_chart", series: [] }} title="Empty chart" />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("暂无可绘制序列")).not.toBeInTheDocument();
    expect(screen.queryByText("chart_series_missing")).not.toBeInTheDocument();
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("renders insufficient-history state instead of drawing one-point series", () => {
    render(
      <MacroTimeSeriesChart
        chart={{
          id: "equity_proxy_performance",
          status: "insufficient_history",
          status_label: "历史样本不足：无法计算 60 日变化",
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
      "历史样本不足：无法计算 60 日变化",
    );
    expect(figure).not.toHaveTextContent("insufficient_history:60d");
    expect(figure).not.toHaveTextContent("insufficient_history");
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("omits under-minimum series from the visible chart legend", () => {
    render(
      <MacroTimeSeriesChart
        chart={{
          id: "mixed_history_chart",
          series: [
            { concept_key: "asset:spx", label: "S&P 500", latest: 110, unit: "index" },
            { concept_key: "rates:dgs10", label: "10Y", latest: 4.1, unit: "percent" },
          ],
        }}
        seriesData={{
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
              points: [{ observed_at: "2026-05-19", value: 4.1 }],
            },
          },
        }}
        title="Mixed history"
      />,
    );

    const figure = screen.getByRole("figure", { name: "Mixed history" });
    expect(within(figure).getByText("S&P 500")).toBeInTheDocument();
    expect(within(figure).queryByText("10Y")).not.toBeInTheDocument();
    expect(figure).not.toHaveTextContent("n/a");
  });

  it("omits insufficient-history chart state without an explicit backend status label", () => {
    const { container } = render(
      <MacroTimeSeriesChart
        chart={{
          id: "equity_proxy_performance",
          status: "insufficient_history",
          series: [{ concept_key: "asset:spx", label: "S&P 500", latest: 110, point_count: 1 }],
        }}
        seriesData={{
          window: "60d",
          data_gaps: [{ code: "insufficient_history:60d" }],
          series: {
            "asset:spx": {
              concept_key: "asset:spx",
              status: "insufficient_history",
              points: [{ observed_at: "2026-05-20", value: 110 }],
            },
          },
        }}
        title="Unlabeled history check"
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("历史样本不足")).not.toBeInTheDocument();
    expect(screen.queryByText("insufficient_history")).not.toBeInTheDocument();
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("does not use series status labels as chart state fallbacks", () => {
    const { container } = render(
      <MacroTimeSeriesChart
        chart={{
          id: "equity_proxy_performance",
          series: [
            {
              concept_key: "asset:spx",
              label: "S&P 500",
              latest: 110,
              point_count: 1,
              status: "insufficient_history",
              status_label: "Series-level status must stay local.",
            },
          ],
        }}
        title="Series-only status"
      />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Series-level status must stay local.")).not.toBeInTheDocument();
    expect(chartMocks.createChart).not.toHaveBeenCalled();
  });

  it("does not expose payload-only chart status labels or units", () => {
    render(
      <MacroTimeSeriesChart
        chart={{
          id: "payload_metadata_chart",
          series: [{ concept_key: "rates:dgs10", label: "10Y", latest: 4.1 }],
        }}
        seriesData={{
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
        }}
        title="Payload metadata"
      />,
    );

    const figure = screen.getByRole("figure", { name: "Payload metadata" });
    expect(figure).not.toHaveTextContent("payload status must stay hidden");
    expect(figure).not.toHaveTextContent("insufficient_history");
    expect(within(figure).getByText("4.1")).toBeInTheDocument();
    expect(figure).not.toHaveTextContent("4.1%");
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
            { concept_key: "rates:dgs10", label: "10Y", latest: 4.2, unit: "percent" },
            { concept_key: "rates:dgs2", label: "2Y", latest: 3.8, unit: "percent" },
            { concept_key: "rates:dgs30", label: "30Y", latest: 4.7, unit: "percent" },
            { concept_key: "rates:dgs5", label: "5Y", latest: 4.0, unit: "percent" },
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

  it("does not render yield curve points from v2 inline observations when latest is missing", () => {
    const { container } = render(
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

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("macro-yield-curve-point")).not.toBeInTheDocument();
    expect(screen.queryByText("10Y")).not.toBeInTheDocument();
    expect(screen.queryByText("4.2%")).not.toBeInTheDocument();
  });

  it("returns no yield-curve chrome when models have no drawable rows", () => {
    const { container } = render(
      <MacroYieldCurveChart chart={{ id: "yield_curve", series: [] }} title="Yield curve" />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("暂无收益率曲线数据")).not.toBeInTheDocument();
    expect(screen.queryByText("yield_curve_points_missing")).not.toBeInTheDocument();
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
