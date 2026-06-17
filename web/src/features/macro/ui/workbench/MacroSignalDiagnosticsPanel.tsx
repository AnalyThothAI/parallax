import type { MacroSignalDiagnostics } from "../../model/macroWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

import "./macroSignalDiagnostics.css";

export function MacroSignalDiagnosticsPanel({
  diagnostics,
}: {
  diagnostics: MacroSignalDiagnostics | null;
}) {
  if (!diagnostics) {
    return null;
  }
  const ariaLabel = diagnostics.label;

  return (
    <MacroPanel
      ariaLabel={ariaLabel}
      className="macro-signal-diagnostics-panel"
      meta={`${diagnostics.rows.length} 条`}
      span="full"
      title={diagnostics.headline}
    >
      <div className="macro-signal-diagnostics">
        {diagnostics.summary ? (
          <p className="macro-signal-diagnostics-summary">{diagnostics.summary}</p>
        ) : null}
        <div className="macro-signal-diagnostics-grid" aria-label={`${ariaLabel}读数`}>
          {diagnostics.rows.map((row) => (
            <article className="macro-signal-diagnostics-row" key={row.key}>
              {row.statusLabel ? <span>{row.statusLabel}</span> : null}
              <b>{row.label}</b>
              <small>{row.value}</small>
            </article>
          ))}
        </div>
        <div className="macro-signal-diagnostics-readouts">
          <SignalDiagnosticsList title="交易含义" items={diagnostics.implications} />
          <SignalDiagnosticsList title="失效条件" items={diagnostics.invalidations} />
        </div>
      </div>
    </MacroPanel>
  );
}

function SignalDiagnosticsList({ items, title }: { items: string[]; title: string }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section className="macro-signal-diagnostics-list" aria-label={title}>
      <h4>{title}</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
