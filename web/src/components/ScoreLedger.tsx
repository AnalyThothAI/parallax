import type { ScoreBlock, TimingBlock, TokenFlowItem } from "../api/types";
import { formatReason, formatRisk, formatScore } from "../lib/format";

type LedgerItem = {
  key: string;
  label: string;
  block: ScoreBlock | TimingBlock;
};

export function ScoreLedger({ token }: { token: TokenFlowItem | null }) {
  if (!token) {
    return null;
  }
  const items: LedgerItem[] = [
    { key: "heat", label: "Heat", block: token.social_heat },
    { key: "quality", label: "Quality", block: token.discussion_quality },
    { key: "propagation", label: "Propagation", block: token.propagation },
    { key: "tradeability", label: "Tradeability", block: token.tradeability },
    { key: "timing", label: "Timing", block: token.timing }
  ];
  return (
    <div className="score-ledger">
      <section className="score-overview">
        <div>
          <span>Opportunity</span>
          <b>{formatScore(token.opportunity.score)}</b>
        </div>
        {Object.entries(token.opportunity.components).map(([key, value]) => (
          <div key={key}>
            <span>{key}</span>
            <b>{formatScore(value)}</b>
          </div>
        ))}
      </section>
      <div className="score-grid">
        {items.map((item) => (
          <article className="score-card" key={item.key}>
            <header>
              <span>{item.label}</span>
              <b>{formatScore(item.block.score)}</b>
            </header>
            <div className="ledger-list">
              {(item.block.contributions ?? []).slice(0, 4).map((entry) => (
                <p key={`${entry.feature}:${entry.reason}`}>
                  <span>{entry.feature}</span>
                  <b>{formatScore(entry.value)}</b>
                  <em>{formatReason(entry.reason)}</em>
                </p>
              ))}
            </div>
            <PillStrip label="reasons" items={item.block.reasons} formatter={formatReason} />
            <PillStrip label="risks" items={item.block.risks} formatter={formatRisk} risk />
            {(item.block.risk_caps ?? []).length ? (
              <div className="risk-cap-list">
                {item.block.risk_caps?.map((cap) => (
                  <span key={`${item.key}:${cap.risk}:${cap.cap}`}>
                    {formatRisk(cap.risk)} cap {formatScore(cap.cap)}
                  </span>
                ))}
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {token.opportunity.hard_risks?.length ? (
        <div className="hard-risk-strip">
          {token.opportunity.hard_risks.map((risk) => (
            <span key={risk}>{formatRisk(risk)}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PillStrip({
  label,
  items,
  formatter,
  risk
}: {
  label: string;
  items: string[];
  formatter: (value: string) => string;
  risk?: boolean;
}) {
  if (!items.length) {
    return null;
  }
  return (
    <div className={`pill-strip ${risk ? "risk" : ""}`} aria-label={label}>
      {items.slice(0, 5).map((item) => (
        <span key={item}>{formatter(item)}</span>
      ))}
    </div>
  );
}
