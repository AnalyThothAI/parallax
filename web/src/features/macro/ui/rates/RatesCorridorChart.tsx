import { useMemo } from "react";

import type { RatesCorridorModel, RatesCorridorSeries } from "../../model/macroRatesChartModel";

const WIDTH = 720;
const HEIGHT = 300;
const PLOT = {
  bottom: 42,
  left: 48,
  right: 28,
  top: 24,
};

const LINE_COLORS: Record<string, string> = {
  effr: "#38bdf8",
  iorb: "#f59e0b",
  sofr: "#34d399",
  sofr_30d: "#f472b6",
};

export function RatesCorridorChart({ model }: { model: RatesCorridorModel }) {
  const geometry = useMemo(() => buildGeometry(model), [model]);

  return (
    <figure aria-label="联邦基金目标走廊" className="macro-rates-corridor">
      <figcaption>联邦基金目标走廊</figcaption>
      {geometry.hasData ? (
        <>
          <svg
            aria-labelledby="rates-corridor-title rates-corridor-desc"
            className="macro-rates-corridor-svg"
            role="img"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          >
            <title id="rates-corridor-title">联邦基金目标走廊</title>
            <desc id="rates-corridor-desc">目标区间与 EFFR、IORB、SOFR 及 SOFR 30D 序列。</desc>
            <line
              className="macro-rates-corridor-axis"
              x1={PLOT.left}
              x2={WIDTH - PLOT.right}
              y1={HEIGHT - PLOT.bottom}
              y2={HEIGHT - PLOT.bottom}
            />
            <line
              className="macro-rates-corridor-axis"
              x1={PLOT.left}
              x2={PLOT.left}
              y1={PLOT.top}
              y2={HEIGHT - PLOT.bottom}
            />
            {geometry.yTicks.map((tick) => (
              <g key={tick.label}>
                <line
                  className="macro-rates-corridor-grid"
                  x1={PLOT.left}
                  x2={WIDTH - PLOT.right}
                  y1={tick.y}
                  y2={tick.y}
                />
                <text className="macro-rates-corridor-tick" x={12} y={tick.y + 4}>
                  {tick.label}
                </text>
              </g>
            ))}
            {geometry.bandPoints ? (
              <polygon
                className="macro-rates-corridor-band"
                data-testid="rates-corridor-band"
                points={geometry.bandPoints}
              />
            ) : null}
            {geometry.lines.map((line) => (
              <polyline
                className="macro-rates-corridor-line"
                data-testid={`rates-corridor-line-${line.key.replace("_", "-")}`}
                key={line.key}
                points={line.points}
                stroke={LINE_COLORS[line.key] ?? "#cbd5e1"}
              />
            ))}
            {geometry.xLabels.map((label) => (
              <text
                className="macro-rates-corridor-date"
                key={label.time}
                textAnchor={label.anchor}
                x={label.x}
                y={HEIGHT - 14}
              >
                {label.text}
              </text>
            ))}
          </svg>
          <div className="macro-rates-corridor-legend">
            {model.lower ? <LegendChip series={model.lower} tone="band" /> : null}
            {model.upper ? <LegendChip series={model.upper} tone="band" /> : null}
            {model.lines.map((series) => (
              <LegendChip key={series.key} series={series} tone={series.key} />
            ))}
          </div>
          {model.missingLabels.length > 0 ? (
            <p className="macro-rates-corridor-missing">待补齐：{model.missingLabels.join("、")}</p>
          ) : null}
        </>
      ) : (
        <div className="macro-rates-empty" role="status">
          暂无可绘制走廊数据
        </div>
      )}
    </figure>
  );
}

function LegendChip({ series, tone }: { series: RatesCorridorSeries; tone: string }) {
  return (
    <span className="macro-rates-corridor-chip" data-tone={tone}>
      <b>{series.label}</b>
      <strong>{formatValue(series.latest, series.unit)}</strong>
    </span>
  );
}

type CorridorGeometry = {
  bandPoints: string | null;
  hasData: boolean;
  lines: Array<{ key: string; points: string }>;
  xLabels: Array<{ anchor: "end" | "middle" | "start"; text: string; time: string; x: number }>;
  yTicks: Array<{ label: string; y: number }>;
};

function buildGeometry(model: RatesCorridorModel): CorridorGeometry {
  const series = [model.lower, model.upper, ...model.lines].filter(
    (item): item is RatesCorridorSeries => Boolean(item),
  );
  const times = uniqueStrings(series.flatMap((item) => item.points.map((point) => point.time)));
  const values = series.flatMap((item) => item.points.map((point) => point.value));
  if (times.length === 0 || values.length === 0) {
    return { bandPoints: null, hasData: false, lines: [], xLabels: [], yTicks: [] };
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max((max - min) * 0.18, 0.08);
  const minValue = min - pad;
  const maxValue = max + pad;
  const xForTime = (time: string) => {
    const index = times.indexOf(time);
    if (times.length === 1) {
      return PLOT.left + (WIDTH - PLOT.left - PLOT.right) / 2;
    }
    return PLOT.left + (index / (times.length - 1)) * (WIDTH - PLOT.left - PLOT.right);
  };
  const yForValue = (value: number) =>
    PLOT.top + ((maxValue - value) / (maxValue - minValue)) * (HEIGHT - PLOT.top - PLOT.bottom);
  const bandPoints = buildBandPoints(model.lower, model.upper, times, xForTime, yForValue);

  return {
    bandPoints,
    hasData: true,
    lines: model.lines.map((line) => ({
      key: line.key,
      points: line.points
        .map((point) => `${xForTime(point.time)},${yForValue(point.value)}`)
        .join(" "),
    })),
    xLabels: axisLabels(times, xForTime),
    yTicks: [minValue, (minValue + maxValue) / 2, maxValue].map((value) => ({
      label: formatValue(value, "percent"),
      y: yForValue(value),
    })),
  };
}

function buildBandPoints(
  lower: RatesCorridorSeries | null,
  upper: RatesCorridorSeries | null,
  times: string[],
  xForTime: (time: string) => number,
  yForValue: (value: number) => number,
): string | null {
  if (!lower || !upper) {
    return null;
  }
  const lowerByTime = new Map(lower.points.map((point) => [point.time, point.value]));
  const upperByTime = new Map(upper.points.map((point) => [point.time, point.value]));
  const paired = times
    .map((time) => {
      const lowerValue = lowerByTime.get(time);
      const upperValue = upperByTime.get(time);
      return lowerValue === undefined || upperValue === undefined
        ? null
        : { lowerValue, time, upperValue };
    })
    .filter((point): point is { lowerValue: number; time: string; upperValue: number } =>
      Boolean(point),
    );
  if (paired.length === 0) {
    return null;
  }
  const upperPoints = paired.map(
    (point) => `${xForTime(point.time)},${yForValue(point.upperValue)}`,
  );
  const lowerPoints = [...paired]
    .reverse()
    .map((point) => `${xForTime(point.time)},${yForValue(point.lowerValue)}`);
  return [...upperPoints, ...lowerPoints].join(" ");
}

function axisLabels(
  times: string[],
  xForTime: (time: string) => number,
): Array<{ anchor: "end" | "middle" | "start"; text: string; time: string; x: number }> {
  const selected = times.length <= 2 ? times : [times[0], times[times.length - 1]];
  return selected.map((time, index) => ({
    anchor: index === 0 ? "start" : index === selected.length - 1 ? "end" : "middle",
    text: time.slice(5) || time,
    time,
    x: xForTime(time),
  }));
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
}

function formatValue(value: number | null, unit: string | null): string {
  if (value === null || value === undefined) {
    return "n/a";
  }
  const formatted = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value);
  return unit === "percent" ? `${formatted}%` : formatted;
}
