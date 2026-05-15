import type { TokenCaseViewModel } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseAmplifiersRail.module.css";

type TokenCaseAmplifiersRailProps = {
  amplifiers: TokenCaseViewModel["amplifiers"];
};

export function TokenCaseAmplifiersRail({ amplifiers }: TokenCaseAmplifiersRailProps) {
  return (
    <section className={styles.rail} aria-labelledby="token-case-amplifiers">
      <header>
        <span>Propagation accounts</span>
        <h2 id="token-case-amplifiers">Key Amplifiers</h2>
      </header>
      <div className={styles.list}>
        {amplifiers.length ? (
          amplifiers.map((account) => (
            <article key={`${account.handle}-${account.role}`}>
              <b>{account.handle}</b>
              <span>{account.role}</span>
              <small>
                {account.posts} posts{account.firstSeenLabel ? ` · ${account.firstSeenLabel}` : ""}
              </small>
            </article>
          ))
        ) : (
          <p>No amplifier cluster</p>
        )}
      </div>
    </section>
  );
}
