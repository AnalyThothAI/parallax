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
    render(<MacroTimeSeriesChart chart={chartFixture()} seriesData={seriesFixture()} title="Equity trend" />);

    const figure = screen.getByRole("figure", { name: "Equity trend" });
    expect(within(figure).getByText("asset:spx")).toBeInTheDocument();
    expect(within(figure).getByText("110")).toBeInTheDocument();
    expect(chartMocks.createChart).toHaveBeenCalledTimes(1);
    expect(chartMocks.lineSeries.setData).toHaveBeenCalled();
  });

  it("keeps an empty chart state accessible without requiring canvas pixels", () => {
    render(<MacroTimeSeriesChart chart={{ chart_id: "empty_chart", series: [] }} title="Empty chart" />);

    expect(screen.getByRole("figure", { name: "Empty chart" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Empty chart state" })).toHaveTextContent("chart_series_missing");
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
          chart_id: "yield_curve",
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

  it("renders a heatmap as an accessible table with raw numeric labels", () => {
    render(
      <MacroHeatmap
        caption="Asset correlation heatmap"
        rows={[
          { concept_key: "asset:spy", label: "SPY", correlations: { "asset:spy": 1, "asset:qqq": 0.92 } },
          { concept_key: "asset:qqq", label: "QQQ", correlations: { "asset:spy": 0.92, "asset:qqq": 1 } },
        ]}
      />,
    );

    const table = screen.getByRole("table", { name: "Asset correlation heatmap" });
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "",
      "SPY",
      "QQQ",
    ]);
    expect(within(table).getAllByText("0.92")).toHaveLength(2);
  });
});

function chartFixture(chartId = "equity_proxy_performance"): MacroModuleChart {
  return {
    chart_id: chartId,
    series: [{ concept_key: "asset:spx", label: "asset:spx", latest: 110, unit: "index" }],
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
