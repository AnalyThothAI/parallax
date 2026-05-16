import type { TokenCasePostEvent } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCasePostEventCard.module.css";

type TokenCasePostEventCardProps = {
  item: TokenCasePostEvent;
};

export function TokenCasePostEventCard({ item }: TokenCasePostEventCardProps) {
  const handle = item.handle ? `@${item.handle.replace(/^@+/, "")}` : "unknown";

  return (
    <article className={styles.card} data-phase={item.phase ?? "unknown"}>
      <div className={styles.timeGutter}>
        <time>{item.timeLabel ?? "--"}</time>
        {item.phase ? <span>{item.phase}</span> : null}
      </div>
      <div className={styles.body}>
        <header className={styles.eventHeader}>
          <div>
            <b>{handle}</b>
            {item.role ? <span>{item.role}</span> : null}
          </div>
          <div className={styles.eventActions}>
            {item.market ? (
              <div className={styles.marketQuote} data-tone={item.market.tone}>
                <span>{item.market.providerLabel}</span>
                <b>{item.market.eventPriceLabel}</b>
                {item.market.liveDeltaLabel ? <em>{item.market.liveDeltaLabel}</em> : null}
              </div>
            ) : null}
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`Open X post by ${handle}`}
              >
                X
              </a>
            ) : null}
          </div>
        </header>
        <div className={styles.pills}>
          {item.pills.map((pill) => (
            <span key={`${item.id}-${pill.label}`} data-tone={pill.tone}>
              {pill.label}
            </span>
          ))}
        </div>
        <p className={styles.text}>{item.text}</p>
        <details className={styles.details}>
          <summary>原文</summary>
          <p>{item.text}</p>
          <dl className={styles.contributions}>
            {item.quality.contributions.map((contribution) => (
              <div key={`${item.id}-${contribution.label}`}>
                <dt>{contribution.label}</dt>
                <dd>
                  <b>{contribution.value}</b>
                  <span>{contribution.reason}</span>
                </dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
    </article>
  );
}
