import type { TokenCaseViewModel } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseBullBearRail.module.css";

type TokenCaseBullBearRailProps = {
  bullBear: TokenCaseViewModel["bullBear"];
};

export function TokenCaseBullBearRail({ bullBear }: TokenCaseBullBearRailProps) {
  const hasBull = hasThesisContent(bullBear.bull);
  const hasBear = hasThesisContent(bullBear.bear);

  return (
    <section className={styles.rail} aria-labelledby="token-case-bull-bear">
      <header>
        <span>{bullBear.stance}</span>
        <h2 id="token-case-bull-bear">Bull/Bear</h2>
      </header>
      {!hasBull && !hasBear ? <p className={styles.empty}>尚无 bull/bear 评估</p> : null}
      <article className={styles.thesis} data-tone={bullBear.bull.tone}>
        <h3>{bullBear.bull.title}</h3>
        {bullBear.bull.thesis ? <p>{bullBear.bull.thesis}</p> : null}
        {bullBear.bull.bullets.length ? (
          <ul>
            {bullBear.bull.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        ) : null}
      </article>
      <article className={styles.thesis} data-tone={bullBear.bear.tone}>
        <h3>{bullBear.bear.title}</h3>
        {bullBear.bear.thesis ? <p>{bullBear.bear.thesis}</p> : null}
        {bullBear.bear.bullets.length ? (
          <ul>
            {bullBear.bear.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        ) : null}
      </article>
    </section>
  );
}

function hasThesisContent(thesis: TokenCaseViewModel["bullBear"]["bull"]): boolean {
  return Boolean(thesis.thesis.trim()) || thesis.bullets.length > 0;
}
