import type { RatesRealRateDiagnostics as RatesRealRateDiagnosticsModel } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./ratesRealRateDiagnostics.css";

export function RatesRealRateDiagnostics({
  diagnostics,
}: {
  diagnostics: RatesRealRateDiagnosticsModel | null;
}) {
  if (!diagnostics) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="实际利率诊断"
      className="macro-rates-real-rate-diagnostics-panel"
      meta={`${diagnostics.realYieldRows.length + diagnostics.inflationRows.length} 条`}
      span="full"
      title={diagnostics.headline}
    >
      <div className="macro-rates-real-rate-diagnostics">
        <p className="macro-rates-real-rate-summary">{diagnostics.summary}</p>
        <div className="macro-rates-real-rate-groups">
          <RateRowGroup label="实际利率曲线" rows={diagnostics.realYieldRows} />
          <RateRowGroup label="通胀补偿" rows={diagnostics.inflationRows} />
        </div>
        <div className="macro-rates-real-rate-readouts">
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

function RateRowGroup({
  label,
  rows,
}: {
  label: string;
  rows: RatesRealRateDiagnosticsModel["realYieldRows"];
}) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <section aria-label={label} className="macro-rates-real-rate-group">
      <h4>{label}</h4>
      <div className="macro-rates-real-rate-grid">
        {rows.map((row) => (
          <article className="macro-rates-real-rate-row" key={row.key}>
            <div>
              <h5>{row.label}</h5>
              {row.statusLabel ? <span>{row.statusLabel}</span> : null}
            </div>
            <strong>{row.value}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}
