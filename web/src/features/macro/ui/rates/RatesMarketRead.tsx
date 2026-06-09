import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesMarketRead({ view }: { view: RatesWorkbenchView }) {
  const asOf = compactAsOfLabel(view.asOfLabel);
  const gapCount = view.missingPrimaryItems.length;
  const proxyNote = view.proxyNote && view.proxyNote !== view.marketHeadline ? view.proxyNote : null;

  return (
    <MacroPanel
      ariaLabel="利率简报"
      className="macro-rates-market-read-panel"
      meta={`${view.readinessLabel} · ${asOf}`}
      span="full"
      title="利率简报"
    >
      <div className="macro-rates-market-read">
        <div className="macro-rates-market-read-head">
          <div>
            <p className="macro-rates-eyebrow">{view.title}</p>
            <h3>{view.marketHeadline}</h3>
          </div>
          <dl className="macro-rates-read-state" aria-label="利率模块状态">
            <div>
              <dt>状态</dt>
              <dd>{view.readinessLabel}</dd>
            </div>
            <div>
              <dt>截至</dt>
              <dd>{asOf}</dd>
            </div>
            <div>
              <dt>缺口</dt>
              <dd>{gapCount > 0 ? `${gapCount} 项` : "0"}</dd>
            </div>
          </dl>
        </div>
        {proxyNote ? <p className="macro-rates-proxy-note">{proxyNote}</p> : null}
        {view.missingPrimaryItems.length > 0 ? (
          <div className="macro-rates-missing-primary">
            <span>明细</span>
            <ul>
              {view.missingPrimaryItems.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </MacroPanel>
  );
}

function compactAsOfLabel(label: string): string {
  return label.replace(/^截至\s*/, "");
}
