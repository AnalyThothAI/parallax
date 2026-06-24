import type { MacroStructuredAnalysis } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroWorkbench.css";

export function MacroStructuredAnalysisPanel({
  analysis,
}: {
  analysis: MacroStructuredAnalysis | null;
}) {
  if (!analysis) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel={analysis.label}
      className="macro-workbench-structured-panel"
      meta={`${analysis.rows.length} 域`}
      span="full"
      title={analysis.label}
    >
      <div className="macro-workbench-structured-grid">
        {analysis.rows.map((row) => (
          <article className="macro-workbench-structured-row" key={row.key}>
            <div className="macro-workbench-structured-head">
              <h4>{row.label}</h4>
              {row.regimeLabel ? <span>{row.regimeLabel}</span> : null}
            </div>
            <p>{row.fact}</p>
            <ul>
              {row.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <small>交易含义：{row.trade}</small>
            <small>失效条件：{row.invalidation}</small>
          </article>
        ))}
      </div>
    </MacroPanel>
  );
}
