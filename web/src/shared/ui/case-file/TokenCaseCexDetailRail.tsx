import type { TokenCaseViewModel } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseCexDetailRail.module.css";

type TokenCaseCexDetailRailProps = {
  cexDetail: NonNullable<TokenCaseViewModel["cexDetail"]>;
};

export function TokenCaseCexDetailRail({ cexDetail }: TokenCaseCexDetailRailProps) {
  return (
    <section className={styles.rail} aria-labelledby="token-case-cex-detail">
      <header>
        <span>{cexDetail.instrumentLabel}</span>
        <h2 id="token-case-cex-detail">CEX Derivatives</h2>
        <p data-tone={cexDetail.tone}>
          {cexDetail.statusLabel}
          {cexDetail.freshnessLabel ? ` · ${cexDetail.freshnessLabel}` : ""}
        </p>
      </header>

      {cexDetail.metrics.length ? (
        <div className={styles.metricGrid}>
          {cexDetail.metrics.map((metric) => (
            <div className={styles.metric} data-tone={metric.tone} key={metric.key}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              <small>{metric.detail}</small>
            </div>
          ))}
        </div>
      ) : null}

      {cexDetail.oiDeltas.length ? (
        <div className={styles.strip} aria-label="Open interest change">
          {cexDetail.oiDeltas.map((delta) => (
            <span data-tone={delta.tone} key={delta.label}>
              <small>{delta.label}</small>
              <strong>{delta.value}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {cexDetail.cvdDeltas.length ? (
        <div className={styles.strip} aria-label="CVD change">
          {cexDetail.cvdDeltas.map((delta) => (
            <span data-tone={delta.tone} key={delta.label}>
              <small>{delta.label}</small>
              <strong>{delta.value}</strong>
            </span>
          ))}
        </div>
      ) : null}

      {cexDetail.levels.length ? (
        <ul className={styles.levels} aria-label="CEX levels">
          {cexDetail.levels.map((level) => (
            <li data-tone={level.tone} key={`${level.kind}:${level.priceLabel}`}>
              <span>{level.kind}</span>
              <strong>{level.priceLabel}</strong>
              {level.scoreLabel ? <small>{level.scoreLabel}</small> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {cexDetail.dataGaps.length ? (
        <ul className={styles.gaps}>
          {cexDetail.dataGaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
