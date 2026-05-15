import type { TokenCaseMarketView } from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseMarketRail.module.css";

type TokenCaseMarketRailProps = {
  market: TokenCaseMarketView;
};

const READINESS_LABELS = ["pricefeed route", "WS subscription", "OHLC"];

export function TokenCaseMarketRail({ market }: TokenCaseMarketRailProps) {
  const ready = market.status === "ready" || market.status === "live";

  return (
    <section className={styles.rail} aria-labelledby="token-case-market">
      <header>
        <span>Market tape</span>
        <h2 id="token-case-market">Live Market</h2>
      </header>
      <div className={styles.priceBlock} data-tone={market.tone}>
        <span>{market.provider ?? "provider missing"}</span>
        <b>{market.priceLabel}</b>
        <p>{market.observedAtLabel ?? market.emptyTitle ?? market.status}</p>
      </div>
      <dl className={styles.facts}>
        <div>
          <dt>market cap</dt>
          <dd>{market.marketCapLabel}</dd>
        </div>
        <div>
          <dt>liquidity</dt>
          <dd>{market.liquidityLabel}</dd>
        </div>
        <div>
          <dt>holders</dt>
          <dd>{market.holdersLabel}</dd>
        </div>
      </dl>
      <div className={styles.readiness}>
        {READINESS_LABELS.map((label) => (
          <span key={label} data-ready={ready ? "true" : "false"}>
            {label}
          </span>
        ))}
      </div>
      {market.emptyDetail ? <p className={styles.detail}>{market.emptyDetail}</p> : null}
    </section>
  );
}
