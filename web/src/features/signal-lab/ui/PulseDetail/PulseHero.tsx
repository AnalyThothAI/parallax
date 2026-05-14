import { formatUtcTimestamp } from "@lib/format";
import type { ReactNode } from "react";

import type { DetailDensity, PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseHero.module.css";

type Props = {
  hero: PulseDetailViewModel["hero"];
  density: DetailDensity;
  actions?: ReactNode;
};

export function PulseHero({ actions, density, hero }: Props) {
  const totalMentions = hero.burstHistogram.bins.reduce((sum, bin) => sum + bin.count, 0);
  const maxCount = Math.max(1, ...hero.burstHistogram.bins.map((bin) => bin.count));
  const anchors = [
    { id: "first", label: "first", at: hero.burstHistogram.firstEventAt },
    { id: "peak", label: "peak", at: hero.burstHistogram.peakAt },
    { id: "now", label: "now", at: hero.burstHistogram.nowAt },
  ].filter((anchor) => anchor.at != null);
  return (
    <header className={styles.hero} data-density={density} aria-label="pulse identity">
      <div className={styles.identity}>
        <h1>{hero.subject.symbol}</h1>
        <p>
          {hero.subject.chain}
          {hero.subject.shortAddress ? ` · ${hero.subject.shortAddress}` : ""}
          {hero.subject.targetMarketType ? ` · ${hero.subject.targetMarketType}` : ""}
        </p>
        <div className={styles.pills}>
          {hero.pills.map((pill) => (
            <span key={pill.id} data-tone={pill.tone}>
              {pill.label}
            </span>
          ))}
        </div>
        <small>candidate · {hero.candidateIdShort}</small>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </div>

      <div className={styles.burst} aria-label="social burst histogram">
        <div className={styles.kicker}>
          social burst · 24h · {totalMentions} mentions · {hero.burstHistogram.uniqueAuthors} authors
        </div>
        <div className={styles.bars}>
          {hero.burstHistogram.bins.map((bin, index) => {
            const isPeak = index === hero.burstHistogram.peakBucketIndex && bin.count > 0;
            const isNow = index === hero.burstHistogram.bins.length - 1;
            return (
              <span
                key={`${bin.startMs}:${index}`}
                data-bar
                data-has={bin.count > 0 ? "true" : "false"}
                data-peak={isPeak ? "true" : "false"}
                data-now={isNow ? "true" : "false"}
                style={{ height: `${bin.count > 0 ? Math.max(8, (bin.count / maxCount) * 100) : 4}%` }}
                title={`${bin.count} mentions`}
              />
            );
          })}
        </div>
        <dl className={styles.burstAnchors}>
          {anchors.map((anchor) => (
            <div key={anchor.id} data-anchor={anchor.id}>
              <dt>{anchor.label}</dt>
              <dd>
                <time>{formatUtcTimestamp(anchor.at, { suffix: false })}</time>
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <dl className={styles.freshness} aria-label="data freshness">
        <div className={styles.kicker}>freshness · UTC</div>
        {hero.freshness.map((row) => (
          <div key={row.label} data-freshness-row data-tone={row.tone}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </header>
  );
}
