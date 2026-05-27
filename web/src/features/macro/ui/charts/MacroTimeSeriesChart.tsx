import type { MacroModuleChart, MacroSeriesData } from "@lib/types";
import {
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

import {
  buildMacroTimeSeriesModel,
  formatMacroChartValue,
  type MacroTimeSeriesModel,
} from "../../model/macroChartModel";

import { observeChartHost } from "./macroChartResize";

import "./macroCharts.css";

const CHART_COLORS = ["#72c7f0", "#f3b95f", "#8ee0a1", "#e8869a", "#c7b5ff", "#f09a66"];

export function MacroTimeSeriesChart({
  chart,
  seriesData,
  title,
}: {
  chart: MacroModuleChart;
  seriesData?: MacroSeriesData | null;
  title: string;
}) {
  const model = useMemo(() => buildMacroTimeSeriesModel(chart, seriesData), [chart, seriesData]);
  return <MacroLineChartFigure model={model} title={title} />;
}

export function MacroLineChartFigure({
  model,
  title,
  valueUnit,
}: {
  model: MacroTimeSeriesModel;
  title: string;
  valueUnit?: string | null;
}) {
  const chartRef = useRef<IChartApi | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const visibleSeries = useMemo(
    () => model.series.filter((series) => series.points.length >= 2),
    [model.series],
  );
  const stateLabel = useMemo(() => chartStateLabel(model), [model]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || visibleSeries.length === 0) {
      return undefined;
    }
    const chart = createChart(container, {
      height: 190,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      grid: {
        horzLines: { color: "rgba(148, 163, 184, 0.14)" },
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      width: container.clientWidth || 640,
    });
    chartRef.current = chart;
    visibleSeries.forEach((series, index) => {
      const line = chart.addSeries(LineSeries, {
        color: CHART_COLORS[index % CHART_COLORS.length],
        lineWidth: 2,
      });
      line.setData(
        series.points.map(
          (point): LineData => ({
            time: point.time as Time,
            value: point.value,
          }),
        ),
      );
    });
    chart.timeScale().fitContent();
    const resizeObserver = observeChartHost(container, chart, 190);
    return () => {
      resizeObserver?.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [visibleSeries]);

  return (
    <figure aria-label={title} className="macro-chart-figure">
      <figcaption>{title}</figcaption>
      {visibleSeries.length > 0 ? (
        <>
          <div className="macro-chart-canvas-host" ref={containerRef} />
          <ChartLegend model={model} valueUnit={valueUnit} />
        </>
      ) : (
        <div aria-label={`${title} state`} className="macro-chart-state-panel" role="status">
          {stateLabel}
        </div>
      )}
    </figure>
  );
}

function chartStateLabel(model: MacroTimeSeriesModel): string {
  if (
    model.status === "insufficient_history" ||
    model.series.some((series) => series.status === "insufficient_history")
  ) {
    return (
      model.statusLabel ??
      model.series.find((series) => series.status === "insufficient_history")?.statusLabel ??
      "历史样本不足"
    );
  }
  return model.statusLabel ?? "暂无可绘制序列";
}

function ChartLegend({
  model,
  valueUnit,
}: {
  model: MacroTimeSeriesModel;
  valueUnit?: string | null;
}) {
  return (
    <div className="macro-chart-legend">
      {model.series.map((series) => {
        const latest = series.points.at(-1)?.value ?? series.latest;
        return (
          <span className="macro-chart-legend-item" key={series.conceptKey}>
            <b>{series.label}</b>
            <strong>
              {latest === null || latest === undefined
                ? "n/a"
                : formatMacroChartValue(latest, valueUnit ?? series.unit)}
            </strong>
          </span>
        );
      })}
    </div>
  );
}
