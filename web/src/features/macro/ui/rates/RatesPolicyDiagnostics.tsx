import type { RatesPolicyDiagnostics as RatesPolicyDiagnosticsModel } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./ratesPolicyDiagnostics.css";

export function RatesPolicyDiagnostics({
  diagnostics,
}: {
  diagnostics: RatesPolicyDiagnosticsModel | null;
}) {
  if (!diagnostics) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="政策走廊诊断"
      className="macro-rates-policy-diagnostics-panel"
      meta={`${diagnostics.rows.length} 条`}
      span="full"
      title={diagnostics.headline}
    >
      <div className="macro-rates-policy-diagnostics">
        <p className="macro-rates-policy-summary">{diagnostics.summary}</p>
        <div className="macro-rates-policy-grid" aria-label="政策走廊读数">
          {diagnostics.rows.map((row) => (
            <article className="macro-rates-policy-row" key={row.key}>
              <div>
                <h4>{row.label}</h4>
                {row.statusLabel ? <span>{row.statusLabel}</span> : null}
              </div>
              <strong>{row.value}</strong>
            </article>
          ))}
        </div>
        <div className="macro-rates-policy-readouts">
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
