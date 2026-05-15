import type {
  TokenCaseScope,
  TokenCaseViewModel,
  TokenCaseWindow,
} from "@shared/model/tokenCaseViewModel";

import styles from "./TokenCaseHero.module.css";

type TokenCaseHeroProps = {
  hero: TokenCaseViewModel["hero"];
  route: TokenCaseViewModel["route"];
  target: TokenCaseViewModel["target"];
  onWindowChange: (window: TokenCaseWindow) => void;
  onScopeChange: (scope: TokenCaseScope) => void;
};

const WINDOWS: TokenCaseWindow[] = ["5m", "1h", "4h", "24h"];
const SCOPES: TokenCaseScope[] = ["all", "watched"];

export function TokenCaseHero({
  hero,
  route,
  target,
  onWindowChange,
  onScopeChange,
}: TokenCaseHeroProps) {
  const mark = target.symbol?.slice(0, 2).toUpperCase() ?? "?";

  return (
    <header className={styles.hero}>
      <div className={styles.mark} aria-hidden="true">
        {hero.logoUrl ? <img src={hero.logoUrl} alt="" /> : <span>{mark}</span>}
      </div>
      <div className={styles.titleBlock}>
        <span className={styles.kicker}>token case file</span>
        <h1>{hero.title}</h1>
        <p>{hero.subtitle}</p>
        <div className={styles.metaRow}>
          {hero.contractLabel ? <code>{hero.contractLabel}</code> : null}
          <span>{target.shortId}</span>
        </div>
      </div>
      <div className={styles.controls}>
        <div className={styles.segmented} role="group" aria-label="case window">
          {WINDOWS.map((window) => (
            <button
              key={window}
              type="button"
              aria-pressed={route.window === window}
              onClick={() => onWindowChange(window)}
            >
              {window}
            </button>
          ))}
        </div>
        <div className={styles.segmented} role="group" aria-label="case scope">
          {SCOPES.map((scope) => (
            <button
              key={scope}
              type="button"
              aria-pressed={route.scope === scope}
              onClick={() => onScopeChange(scope)}
            >
              {scope}
            </button>
          ))}
        </div>
        <nav className={styles.actions} aria-label="Token links">
          {hero.actions.map((action) => (
            <a key={`${action.label}-${action.href}`} href={action.href} data-tone={action.tone}>
              {action.label}
            </a>
          ))}
          <a href={route.searchHref} data-tone="info">
            Search
          </a>
        </nav>
      </div>
    </header>
  );
}
