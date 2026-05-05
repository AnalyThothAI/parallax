import type { HarnessCreditItem } from "../api/types";
import { formatPercentShare, formatScore } from "../lib/format";
import { signalLabLabel } from "../lib/signalLab";

type CreditLedgerProps = {
  credits: HarnessCreditItem[];
};

export function CreditLedger({ credits }: CreditLedgerProps) {
  return (
    <div className="credit-ledger ledger-box">
      <h3>Credit Rows</h3>
      <p className="ledger-note">Predictive credit, not causal proof.</p>
      {credits.length === 0 ? <div className="empty-state">credit not assigned</div> : null}
      {credits.map((credit) => (
        <article className="credit-row" key={credit.credit_id}>
          <strong>
            {credit.event_type} · {signalLabLabel(credit.source)}
          </strong>
          <span>{credit.horizon}</span>
          <b>{formatScore(credit.event_score * 100)}</b>
          <b>{formatPercentShare(credit.responsibility)}</b>
          <b className={credit.credit >= 0 ? "positive" : "negative"}>{credit.credit.toFixed(3)}</b>
        </article>
      ))}
    </div>
  );
}
