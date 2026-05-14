import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseMarketContext.module.css";

type Props = {
  market: PulseDetailViewModel["market"];
};

export function PulseMarketContext({ market }: Props) {
  return (
    <section className={styles.market} aria-label="market context">
      <dl>
        {market.metrics.map((metric) => (
          <div key={metric.id} data-tone={metric.tone}>
            <dt>{metric.label}</dt>
            <dd>
              <strong>{metric.value}</strong>
              {metric.subValue ? <small>{metric.subValue}</small> : null}
            </dd>
          </div>
        ))}
      </dl>
      {market.staleNotice ? <p>{market.staleNotice}</p> : null}
    </section>
  );
}
