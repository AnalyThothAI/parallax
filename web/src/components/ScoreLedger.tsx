import type { ScoreBlock, TimingBlock, TokenFlowItem } from "@lib/types";

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
    { key: "timing", label: "Timing", block: token.timing },
  ];
  const alphaComponents = [
    ["heat", token.opportunity.components.heat],
    ["quality", token.opportunity.components.quality],
    ["propagation", token.opportunity.components.propagation],
    ["timing", token.opportunity.components.timing],
  ] as const;
  const healthWarnings = dataHealthWarnings(token.factor_data_health);
  return (
    <div className="score-ledger">
      <section className="score-health">
        <div>
          <span>score type</span>
          <b>deterministic ranking</b>
        </div>
        <div>
          <span>baseline</span>
          <b>
            {token.flow.baseline_status} · n{token.flow.baseline_sample_count}
          </b>
        </div>
        <div>
          <span>market</span>
          <b>{token.factor_data_health?.market ?? token.market.price_change_status}</b>
        </div>
        <div>
          <span>rank</span>
          <b>
            {rankValue(
              token.factor_normalization?.alpha_rank,
              token.factor_normalization?.cohort_size,
            )}
          </b>
        </div>
        <div>
          <span>evidence</span>
          <b>{token.evidence_total_count} posts</b>
        </div>
      </section>
      {(token.factor_gates?.blocked_reasons ?? token.opportunity.hard_risks ?? []).length ? (
        <div className="hard-risk-strip">
          {(token.factor_gates?.blocked_reasons ?? token.opportunity.hard_risks ?? []).map(
            (risk) => (
              <span key={risk}>{formatRisk(risk)}</span>
            ),
          )}
        </div>
      ) : null}
      {token.factor_gates ? (
        <section className="score-overview">
          <div>
            <span>Gate</span>
            <b>{token.factor_gates.eligible_for_high_alert ? "eligible" : "blocked"}</b>
          </div>
          <div>
            <span>max decision</span>
            <b>{token.factor_gates.max_decision ?? "-"}</b>
          </div>
          <div>
            <span>identity</span>
            <b>{token.factor_data_health?.identity ?? "-"}</b>
          </div>
          <div>
            <span>alpha</span>
            <b>{token.factor_data_health?.alpha ?? "-"}</b>
          </div>
        </section>
      ) : null}
      {healthWarnings.length ? (
        <div className="hard-risk-strip">
          {healthWarnings.map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}
      {token.opportunity.risk_caps.length ? (
        <div className="risk-cap-list opportunity-caps">
          {token.opportunity.risk_caps.map((cap) => (
            <span key={`opportunity:${cap.risk}:${cap.cap}`}>
              {formatRisk(cap.risk)} cap {formatScore(cap.cap)}
            </span>
          ))}
        </div>
      ) : null}
      <section className="score-overview">
        <div>
          <span>Opportunity</span>
          <b>{formatScore(token.opportunity.score)}</b>
        </div>
        {alphaComponents.map(([key, value]) => (
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
    </div>
  );
}

function dataHealthWarnings(dataHealth: TokenFlowItem["factor_data_health"]): string[] {
  if (!dataHealth) {
    return [];
  }
  return Object.entries(dataHealth)
    .filter(([, status]) => typeof status === "string" && status !== "ready")
    .map(([key, status]) => `${key}:${status}`);
}

function rankValue(rank: unknown, cohortSize: unknown): string {
  const parsedRank = typeof rank === "number" && Number.isFinite(rank) ? rank : null;
  const parsedCohortSize =
    typeof cohortSize === "number" && Number.isFinite(cohortSize) ? cohortSize : null;
  if (parsedRank === null) {
    return "-";
  }
  return parsedCohortSize === null ? `#${parsedRank}` : `#${parsedRank} / ${parsedCohortSize}`;
}

function PillStrip({
  label,
  items,
  formatter,
  risk,
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
