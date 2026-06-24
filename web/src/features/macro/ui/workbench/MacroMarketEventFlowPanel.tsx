import type { MacroMarketEventFlow } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroWorkbench.css";

export function MacroMarketEventFlowPanel({ flow }: { flow: MacroMarketEventFlow | null }) {
  if (!flow) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel={flow.label}
      className="macro-workbench-event-flow-panel"
      meta={`${flow.rows.length} 条`}
      span="full"
      title={flow.label}
    >
      <ul className="macro-workbench-event-flow-list">
        {flow.rows.map((row) => (
          <li key={row.key}>
            {row.meta ? <span>{row.meta}</span> : null}
            <b>{row.label}</b>
            <small>{row.detail}</small>
            {row.impactLabel ? <small>{row.impactLabel}</small> : null}
            <small>{row.watch}</small>
            {row.sourceUrl ? (
              <a
                className="macro-workbench-event-source-link"
                href={row.sourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                来源
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </MacroPanel>
  );
}
