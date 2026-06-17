import type { RatesFact } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";

export function RatesFactStrip({ facts }: { facts: RatesFact[] }) {
  if (facts.length === 0) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="关键事实"
      className="macro-rates-fact-strip macro-rates-fact-panel"
      meta={`${facts.length} 项`}
      span="full"
      title="关键事实"
    >
      <div className="macro-rates-fact-grid">
        {facts.map((fact) => {
          const hasMeta = Boolean(fact.sourceLabel || fact.observedAtLabel || fact.statusLabel);
          return (
            <article className="macro-rates-fact" key={fact.key}>
              <div className="macro-rates-fact-main">
                <span>{fact.label}</span>
                <strong>{fact.value}</strong>
              </div>
              {hasMeta ? (
                <dl className="macro-rates-fact-meta" aria-label={`${fact.label}元信息`}>
                  {fact.sourceLabel ? (
                    <div>
                      <dt>来源</dt>
                      <dd>{fact.sourceLabel}</dd>
                    </div>
                  ) : null}
                  {fact.observedAtLabel ? (
                    <div>
                      <dt>日期</dt>
                      <dd>{fact.observedAtLabel}</dd>
                    </div>
                  ) : null}
                  {fact.statusLabel ? (
                    <div>
                      <dt>状态</dt>
                      <dd>{fact.statusLabel}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : null}
              {fact.interpretation ? (
                <p className="macro-rates-fact-note">{fact.interpretation}</p>
              ) : null}
            </article>
          );
        })}
      </div>
    </MacroPanel>
  );
}
