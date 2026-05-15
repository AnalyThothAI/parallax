import styles from "./TokenCaseDataGapsRail.module.css";

type TokenCaseDataGapsRailProps = {
  dataGaps: string[];
};

export function TokenCaseDataGapsRail({ dataGaps }: TokenCaseDataGapsRailProps) {
  return (
    <section className={styles.rail} aria-labelledby="token-case-data-gaps">
      <header>
        <span>Open fields</span>
        <h2 id="token-case-data-gaps">Data Gaps</h2>
      </header>
      {dataGaps.length ? (
        <ul>
          {dataGaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
      ) : (
        <p>No reported gaps</p>
      )}
    </section>
  );
}
