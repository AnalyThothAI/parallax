import type { TokenCaseViewModel } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCasePropagationSummary.module.css";

type TokenCasePropagationSummaryProps = {
  propagation: TokenCaseViewModel["propagation"];
};

export function TokenCasePropagationSummary({ propagation }: TokenCasePropagationSummaryProps) {
  return (
    <section className={styles.summary} aria-labelledby="token-case-propagation">
      <div className={styles.summaryHead}>
        <h2 id="token-case-propagation">Propagation Summary</h2>
        <p>{propagation.summaryZh}</p>
        <div className={styles.statusPills}>
          {propagation.statusPills.map((pill) => (
            <span key={pill.label} className={styles.pill} data-tone={pill.tone}>
              {pill.label}
            </span>
          ))}
        </div>
      </div>
      <div className={styles.stages}>
        {propagation.stages.map((stage) => (
          <article key={stage.id} className={styles.stage} data-tone={stage.tone}>
            <header>
              <h3>{stage.phase}</h3>
              <span>{stage.count} posts</span>
            </header>
            <p>{stage.readZh}</p>
            <footer>
              <span>{stage.authors} authors</span>
              {stage.leadAccount ? <b>{stage.leadAccount}</b> : null}
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}
