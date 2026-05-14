import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseFactorFamilies.module.css";

type Props = {
  families: PulseDetailViewModel["families"];
};

export function PulseFactorFamilies({ families }: Props) {
  return (
    <section className={styles.families} aria-label="factor families">
      {families.map((family) => (
        <article key={family.id} data-tone={family.scoreTone}>
          <header>
            <div>
              <h2>{family.name}</h2>
              <p>{family.rankLabel}</p>
            </div>
            <strong>{family.score}</strong>
          </header>
          <span className={styles.health}>data_health · {family.dataHealth}</span>
          <dl>
            {family.breakdown.map((row) => (
              <div key={row.label} data-tone={row.tone}>
                <dt>{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </section>
  );
}
