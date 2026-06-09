import type { MacroWorkbenchBrief } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroWorkbench.css";

export function MacroInsightBrief({
  ariaLabel,
  brief,
  title,
}: {
  ariaLabel: string;
  brief: MacroWorkbenchBrief;
  title: string;
}) {
  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-brief-panel"
      meta={brief.statusLabel ?? brief.asOfLabel}
      span="full"
      title={title}
    >
      <div className="macro-workbench-brief">
        <p className="macro-workbench-brief-summary">{brief.summary}</p>
        <dl className="macro-workbench-brief-grid" aria-label={`${title}要点`}>
          {brief.rows.map((row) => (
            <div className="macro-workbench-brief-row" key={row.key}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
          {brief.asOfLabel ? (
            <div className="macro-workbench-brief-row">
              <dt>截至</dt>
              <dd>{brief.asOfLabel}</dd>
            </div>
          ) : null}
        </dl>
      </div>
    </MacroPanel>
  );
}
