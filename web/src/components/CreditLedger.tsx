import type { HarnessCreditItem } from "../api/types";
import { formatPercentShare, formatRelativeTime, formatScore } from "../lib/format";
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
          <strong>{signalLabLabel(credit.credit_id)}</strong>
          <span>{signalLabLabel(credit.cluster_id)}</span>
          <span>
            {signalLabLabel(credit.source)} · {credit.event_type}
          </span>
          <span>
            {credit.asset} · {credit.horizon}
          </span>
          <b>{formatScore(credit.event_score * 100)}</b>
          <b>{formatPercentShare(credit.responsibility)}</b>
          <b className={credit.credit >= 0 ? "positive" : "negative"}>{credit.credit.toFixed(3)}</b>
          <span>{formatRelativeTime(credit.created_at_ms)}</span>
        </article>
      ))}
    </div>
  );
}
