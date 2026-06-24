import type { CSSProperties } from "react";

import type { RatesCurveDiagnostics as RatesCurveDiagnosticsModel } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./ratesCurveDiagnostics.css";

export function RatesCurveDiagnostics({
  diagnostics,
}: {
  diagnostics: RatesCurveDiagnosticsModel | null;
}) {
  if (!diagnostics) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="曲线诊断"
      className="macro-rates-curve-diagnostics-panel"
      meta={`${diagnostics.rows.length} 条`}
      span="full"
      title={diagnostics.headline}
    >
      <div className="macro-rates-curve-diagnostics">
        <p className="macro-rates-curve-summary">{diagnostics.summary}</p>
        <div className="macro-rates-curve-grid">
          {diagnostics.rows.map((row) => (
            <article className="macro-rates-curve-row" key={row.key}>
              <div>
                <h4>{row.label}</h4>
                {row.statusLabel ? <span>{row.statusLabel}</span> : null}
              </div>
              <strong>{row.value}</strong>
            </article>
          ))}
        </div>
        <SpreadHistorySection diagnostics={diagnostics} />
        <TenorComparisonSection diagnostics={diagnostics} />
        <div className="macro-rates-curve-readouts">
          <section aria-label="交易含义">
            <h4>交易含义</h4>
            <ul>
              {diagnostics.implications.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
          <section aria-label="失效条件">
            <h4>失效条件</h4>
            <ul>
              {diagnostics.invalidations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </MacroPanel>
  );
}

function SpreadHistorySection({ diagnostics }: { diagnostics: RatesCurveDiagnosticsModel }) {
  if (diagnostics.spreadHistories.length === 0) {
    return null;
  }

  return (
    <section aria-label="历史利差" className="macro-rates-curve-history">
      <h4>历史利差</h4>
      <div className="macro-rates-curve-history-grid">
        {diagnostics.spreadHistories.map((series) => (
          <article className="macro-rates-curve-history-card" key={series.key}>
            <header>
              <div>
                <h5>{series.label} 历史</h5>
                <span>{series.range}</span>
              </div>
              <strong>{series.latest}</strong>
            </header>
            <div
              aria-label={`${series.label} ${series.range}`}
              className="macro-rates-curve-sparkbars"
              role="img"
            >
              {series.points.map((point) => (
                <span
                  aria-hidden="true"
                  className="macro-rates-curve-sparkbar"
                  key={point.key}
                  style={sparkbarStyle(point.value, series.points)}
                  title={point.label}
                />
              ))}
            </div>
            <ol>
              {series.points.map((point) => (
                <li key={point.key}>{point.label}</li>
              ))}
            </ol>
          </article>
        ))}
      </div>
    </section>
  );
}

function TenorComparisonSection({ diagnostics }: { diagnostics: RatesCurveDiagnosticsModel }) {
  if (diagnostics.tenorComparison.length === 0) {
    return null;
  }

  return (
    <section aria-label="期限拆分" className="macro-rates-curve-tenors">
      <h4>期限拆分</h4>
      <div className="macro-rates-curve-tenor-grid">
        {diagnostics.tenorComparison.map((row) => (
          <article className="macro-rates-curve-tenor-row" key={row.key}>
            <header>
              <h5>{row.label}</h5>
              {row.driverLabel ? <span>{row.driverLabel}</span> : null}
            </header>
            <strong>{row.value}</strong>
            {row.change ? <p>{row.change}</p> : null}
            {row.residual ? <small>{row.residual}</small> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function sparkbarStyle(
  value: number,
  points: Array<{ value: number }>,
): CSSProperties & Record<"--macro-rates-spark-level", string> {
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const level = max === min ? 0.5 : (value - min) / (max - min);
  return { "--macro-rates-spark-level": String(level) };
}
