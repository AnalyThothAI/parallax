import { Brain } from "lucide-react";
import type { AttentionFrontierItem, Decision, TokenFlowItem } from "../api/types";
import {
  compactNumber,
  formatHeatStatus,
  formatPercentShare,
  formatPropagationPhase,
  formatReason,
  formatRisk,
  formatScore,
  formatScoreDelta,
  formatSignedPercent,
  formatTimingStatus,
  formatUsdCompact,
  shortAddress,
  tokenLabel
} from "../lib/format";
import { DecisionTag } from "./DecisionTag";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  decision: Decision;
  manualDecision?: Decision;
  narrativeLink?: AttentionFrontierItem;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({
  item,
  selected,
  decision,
  manualDecision,
  narrativeLink,
  onSelect
}: TokenRadarRowProps) {
  const delta = formatSignedPercent(item.market.price_change_window_pct);
  const direction = delta.startsWith("+") ? "up" : delta.startsWith("-") ? "down" : "flat";
  const topReason = item.discussion_quality.reasons[0] ?? item.discussion_quality.risks[0];
  const heatDelta = formatScoreDelta(item.social_heat.mention_delta);
  return (
    <button
      aria-label={`select token ${tokenLabel(item)}`}
      className={`radar-row ${selected ? "is-selected" : ""}`}
      type="button"
      onClick={() => onSelect(item)}
    >
      <span className="token-cell">
        <strong className="token-symbol">
          <span className="symbol-line">
            <span>{tokenLabel(item)}</span>
            {narrativeLink ? (
              <span className="narrative-link-badge" title={narrativeLink.seed.display?.headline_zh || narrativeLink.seed.narrative_label}>
                <Brain aria-hidden />
              </span>
            ) : null}
          </span>
          <small>
            {item.identity.chain ?? "unknown"} · {shortAddress(item.identity.address ?? item.identity.identity_key)}
          </small>
        </strong>
      </span>

      <span className="metric heat-metric">
        <b>{formatScore(item.social_heat.score)}</b>
        <small>
          {compactNumber(item.social_heat.mentions)} / {heatDelta} · {formatHeatStatus(item.social_heat.status)}
        </small>
      </span>

      <span className="metric">
        <b>{formatScore(item.discussion_quality.score)}</b>
        <small>{topReason ? formatReason(topReason) : "质量待确认"}</small>
      </span>

      <span className="metric propagation-cell">
        <b>{formatPropagationPhase(item.propagation.phase)}</b>
        <small>
          {compactNumber(item.propagation.independent_authors)} 作者 · top {formatPercentShare(item.propagation.top_author_share)}
        </small>
      </span>

      <span className="metric market-cell">
        <b>{formatUsdCompact(item.market.market_cap)}</b>
        <small className={`direction ${direction}`}>{delta}</small>
      </span>

      <span className="metric">
        <b>{formatTimingStatus(item.timing.status)}</b>
        <small>{item.timing.chase_risk ? formatRisk("price_leads_social") : item.market.market_status}</small>
      </span>

      <span className="decision-cell">
        <DecisionTag decision={decision} manual={Boolean(manualDecision)} />
      </span>
    </button>
  );
}
