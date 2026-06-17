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
  if (!brief.summary && brief.rows.length === 0) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-workbench-brief-panel"
      meta={briefMeta(brief)}
      span="full"
      title={title}
    >
      <div className="macro-workbench-brief">
        {brief.summary ? <p className="macro-workbench-brief-summary">{brief.summary}</p> : null}
        {brief.rows.length > 0 ? (
          <dl className="macro-workbench-brief-grid" aria-label={`${title}要点`}>
            {brief.rows.map((row) => (
              <div className="macro-workbench-brief-row" key={row.key}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </MacroPanel>
  );
}

function briefMeta(brief: MacroWorkbenchBrief): string | null {
  const parts = [brief.statusLabel, brief.asOfLabel?.replace(/^截至\s*/, "")]
    .filter((part): part is string => Boolean(part && part.trim()))
    .slice(0, 2);
  return parts.length ? parts.join(" · ") : null;
}
