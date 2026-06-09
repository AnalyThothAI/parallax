import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesMarketRead({ view }: { view: RatesWorkbenchView }) {
  return (
    <MacroPanel
      ariaLabel="利率简报"
      className="macro-rates-market-read-panel"
      meta={view.readinessLabel}
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
              <dt>问题</dt>
              <dd>{view.question}</dd>
            </div>
            <div>
              <dt>准备度</dt>
              <dd>{view.readinessLabel}</dd>
            </div>
            <div>
              <dt>截至</dt>
              <dd>{view.asOfLabel}</dd>
            </div>
          </dl>
        </div>
        <p className="macro-rates-market-copy">{view.marketExplanation}</p>
        {view.proxyNote ? <p className="macro-rates-proxy-note">{view.proxyNote}</p> : null}
        {view.missingPrimaryItems.length > 0 ? (
          <div className="macro-rates-missing-primary">
            <span>待补齐</span>
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
