import type { MacroModuleChart } from "@lib/types";
import {
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

import { buildMacroYieldCurveModel, formatMacroChartValue } from "../../model/macroChartModel";

import { observeChartHost } from "./macroChartResize";

import "./macroCharts.css";

export function MacroYieldCurveChart({ chart, title }: { chart: MacroModuleChart; title: string }) {
  const model = useMemo(() => buildMacroYieldCurveModel(chart), [chart]);
  const points = useMemo(() => model.points, [model.points]);
  const chartRef = useRef<IChartApi | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length === 0) {
      return undefined;
    }
    const chartApi = createChart(container, {
      height: 160,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      width: container.clientWidth || 560,
    });
    chartRef.current = chartApi;
    const line = chartApi.addSeries(LineSeries, { color: "#72c7f0", lineWidth: 2 });
    line.setData(
      points.map(
        (point, index): LineData => ({
          time: `2026-01-${String(index + 1).padStart(2, "0")}` as Time,
          value: point.value,
        }),
      ),
    );
    chartApi.timeScale().fitContent();
    const resizeObserver = observeChartHost(container, chartApi, 160);
    return () => {
      resizeObserver?.disconnect();
      chartApi.remove();
      chartRef.current = null;
    };
  }, [points]);

  return (
    <figure aria-label={title} className="macro-chart-figure">
      <figcaption>{title}</figcaption>
      {points.length > 0 ? (
        <>
          <div className="macro-chart-canvas-host macro-yield-chart-host" ref={containerRef} />
          <div className="macro-yield-curve-points">
            {points.map((point) => (
              <span data-testid="macro-yield-curve-point" key={point.conceptKey}>
                <b>{point.label}</b>
                <strong>{formatMacroChartValue(point.value, point.unit)}</strong>
              </span>
            ))}
          </div>
        </>
      ) : (
        <div aria-label={`${title} state`} className="macro-chart-state-panel" role="status">
          暂无收益率曲线数据
        </div>
      )}
    </figure>
  );
}
