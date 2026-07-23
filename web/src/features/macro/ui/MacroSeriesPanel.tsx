import { useState } from "react";

import { useMacroSeriesQuery } from "../api/useMacroSeriesQuery";
import { formatMacroNumber, macroConceptLabel, macroUnitLabel } from "../model/macroDisplay";
import type { MacroSeriesData } from "../model/macroTypes";

import "./MacroSeriesPanel.css";

export function MacroSeriesPanel({
  conceptKeys,
  token,
  title = "核心走势",
}: {
  conceptKeys: string[];
  token: string;
  title?: string;
}) {
  const [window, setWindow] = useState<"20d" | "60d">("60d");
  const query = useMacroSeriesQuery({ conceptKeys, token, window });

  return (
    <section className="macro-series-panel" aria-labelledby="macro-series-title">
      <header>
        <div>
          <span>同尺度小图 · 单位分离</span>
          <h2 id="macro-series-title">{title}</h2>
        </div>
        <div aria-label="图表窗口" className="macro-series-window" role="group">
          {(["20d", "60d"] as const).map((value) => (
            <button
              aria-pressed={window === value}
              key={value}
              onClick={() => setWindow(value)}
              type="button"
            >
              {value === "20d" ? "20 日" : "60 日"}
            </button>
          ))}
        </div>
      </header>

      {query.isError ? <p role="alert">走势图暂不可用。</p> : null}
      {query.isLoading || !query.data ? (
        <p aria-live="polite">加载走势图…</p>
      ) : (
        <div className="macro-series-grid">
          {conceptKeys.map((conceptKey) => (
            <SeriesFigure
              conceptKey={conceptKey}
              key={conceptKey}
              series={query.data?.series[conceptKey]}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function SeriesFigure({
  conceptKey,
  series,
}: {
  conceptKey: string;
  series: MacroSeriesData["series"][string] | undefined;
}) {
  const numericPoints =
    series?.points.filter(
      (point): point is typeof point & { value: number } => typeof point.value === "number",
    ) ?? [];
  if (!series || series.status !== "ok" || numericPoints.length === 0) {
    return (
      <figure className="macro-series-figure is-unavailable">
        <figcaption>
          <b>{macroConceptLabel(conceptKey)}</b>
          <span>数据不可用</span>
        </figcaption>
      </figure>
    );
  }

  const values = numericPoints.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 240;
  const height = 64;
  const points = values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * (height - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  const latest = numericPoints.at(-1);

  return (
    <figure className="macro-series-figure">
      <figcaption>
        <span>
          <b>{macroConceptLabel(conceptKey)}</b>
          <small>{series.sources.join(" · ")}</small>
        </span>
        <span>
          <strong>{formatMacroNumber(latest?.value ?? null)}</strong>
          <small>{macroUnitLabel(series.unit)}</small>
        </span>
      </figcaption>
      <svg
        aria-label={`${macroConceptLabel(conceptKey)}走势`}
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <line x1="0" x2={width} y1={height - 4} y2={height - 4} />
        <polyline points={points} />
      </svg>
      <div>
        <span>{numericPoints[0]?.observed_at}</span>
        <span>截至 {latest?.observed_at}</span>
      </div>
    </figure>
  );
}
