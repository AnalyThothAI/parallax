import type { TokenCaseMetric } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseMetricStrip.module.css";

type TokenCaseMetricStripProps = {
  metrics: TokenCaseMetric[];
};

export function TokenCaseMetricStrip({ metrics }: TokenCaseMetricStripProps) {
  return (
    <div className={styles.metrics} aria-label="Token case metrics">
      {metrics.map((metric) => (
        <article key={metric.key} className={styles.metric} data-tone={metric.tone}>
          <span>{metric.label}</span>
          <b>{metric.value}</b>
          <p>{metric.detail}</p>
        </article>
      ))}
    </div>
  );
}
