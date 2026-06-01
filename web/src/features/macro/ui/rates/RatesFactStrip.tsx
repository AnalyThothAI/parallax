import type { RatesFact } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesFactStrip({ facts }: { facts: RatesFact[] }) {
  return (
    <MacroPanel
      ariaLabel="关键事实"
      className="macro-rates-fact-panel"
      meta={`${facts.length} 项`}
      span="full"
      title="关键事实"
    >
      {facts.length > 0 ? (
        <div className="macro-rates-fact-grid">
          {facts.map((fact) => (
            <article className="macro-rates-fact" key={fact.key}>
              <div className="macro-rates-fact-main">
                <span>{fact.label}</span>
                <strong>{fact.value}</strong>
              </div>
              <dl className="macro-rates-fact-meta" aria-label={`${fact.label}元信息`}>
                <div>
                  <dt>来源</dt>
                  <dd>{fact.sourceLabel ?? "暂无来源"}</dd>
                </div>
                <div>
                  <dt>日期</dt>
                  <dd>{fact.observedAtLabel}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>{fact.statusLabel ?? "暂无状态"}</dd>
                </div>
              </dl>
              {fact.interpretation ? (
                <p className="macro-rates-fact-note">{fact.interpretation}</p>
              ) : null}
            </article>
          ))}
        </div>
      ) : (
        <div className="macro-rates-empty" role="status">
          暂无关键事实
        </div>
      )}
    </MacroPanel>
  );
}
