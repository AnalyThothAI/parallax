import type { TokenFlowItem } from "../api/types";
import {
  compactNumber,
  formatPercentShare,
  formatRisk,
  formatScore,
  formatScoreDelta,
  formatSignedPercent,
  formatUsdCompact,
  shortAddress,
  tokenLabel
} from "../lib/format";
import { tokenVenueAction } from "../lib/venue";
import { DecisionTag } from "./DecisionTag";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({ item, selected, onSelect }: TokenRadarRowProps) {
  const delta = formatSignedPercent(item.market.price_change_since_social_pct);
  const direction = delta.startsWith("+") ? "up" : delta.startsWith("-") ? "down" : "flat";
  const venueAction = tokenVenueAction(item);
  return (
    <div className={`radar-row ${selected ? "selected" : ""}`}>
      <button
        aria-label={`select token ${tokenLabel(item)}`}
        className={`radar-row-select ${selected ? "selected" : ""}`}
        type="button"
        onClick={() => onSelect(item)}
      >
        <span className="token-cell">
          <strong className="token-symbol">
            <span className="symbol-line">
              <span>{tokenLabel(item)}</span>
            </span>
              <small>{identitySubtitle(item)}</small>
          </strong>
        </span>

        <span className="metric heat-cell" data-radar-metric="heat">
          <b className={scoreClass(item.social_heat.score)}>{heatTitle(item)}</b>
          <small>{heatMeta(item)}</small>
          <Barline score={item.social_heat.score} />
        </span>

        <span className="metric quality-cell" data-radar-metric="quality">
          <b className={scoreClass(item.discussion_quality.score)}>{qualityTitle(item)}</b>
          <small>{qualityMeta(item)}</small>
        </span>

        <span className="phase propagation-cell" data-radar-metric="propagation">
          <b>{propagationTitle(item)}</b>
          <small>{propagationMeta(item)}</small>
        </span>

        <span className="metric market-cell" data-radar-metric="market">
          <b>{marketPrimary(item)}</b>
          <small className={`direction ${direction}`}>{delta} {item.market.market_status}</small>
        </span>

        <span className="phase timing-cell" data-radar-metric="timing">
          <b>{timingTitle(item)}</b>
          <small>{timingMeta(item)}</small>
        </span>

        <span className="decision-cell">
          <DecisionTag decision={item.opportunity.decision} />
        </span>
      </button>

      <span className="venue-cell" data-radar-action="venue">
        {venueAction ? (
          <a aria-label={`Open ${tokenLabel(item)} on ${venueAction.label}`} className="venue-link" href={venueAction.url} rel="noreferrer" target="_blank">
            {venueAction.label}
          </a>
        ) : (
          <span className="muted">-</span>
        )}
      </span>
    </div>
  );
}

function heatTitle(item: TokenFlowItem): string {
  return `${formatScore(item.social_heat.score)} · ${compactNumber(item.social_heat.mentions)} ${formatScoreDelta(item.social_heat.mention_delta)}`;
}

function identitySubtitle(item: TokenFlowItem): string {
  if (item.identity.venue_type === "cex") {
    return [item.identity.exchange?.toUpperCase(), item.identity.inst_id].filter(Boolean).join(" · ") || "CEX";
  }
  return `${item.identity.chain ?? "unknown"} · ${shortAddress(item.identity.address ?? item.identity.identity_key)}`;
}

function marketPrimary(item: TokenFlowItem): string {
  if (item.market.market_cap !== null && item.market.market_cap !== undefined) {
    return formatUsdCompact(item.market.market_cap);
  }
  if (item.market.price !== null && item.market.price !== undefined) {
    return formatUsdCompact(item.market.price);
  }
  return "-";
}

function heatMeta(item: TokenFlowItem): string {
  return `${compactNumber(item.social_heat.mentions)} posts · ${heatEvidence(item)} · share ${formatPercentShare(item.social_heat.stream_share)}`;
}

function heatEvidence(item: TokenFlowItem): string {
  if (item.social_heat.z_score !== null && item.social_heat.z_score !== undefined) {
    return `z${trimDecimal(item.social_heat.z_score)}`;
  }
  if (item.social_heat.new_burst_score !== null && item.social_heat.new_burst_score !== undefined) {
    return "new burst";
  }
  return compactLabel(item.social_heat.status);
}

function qualityTitle(item: TokenFlowItem): string {
  return `${formatScore(item.discussion_quality.score)} · ${qualityLabel(item)}`;
}

function qualityMeta(item: TokenFlowItem): string {
  return `dup ${formatPercentShare(item.discussion_quality.duplicate_text_share)} · info ${compactNumber(item.discussion_quality.informative_post_count)}`;
}

function qualityLabel(item: TokenFlowItem): string {
  const reason = item.discussion_quality.reasons[0] ?? item.discussion_quality.risks[0] ?? "";
  const labels: Record<string, string> = {
    resolved_direct_evidence: "CA direct",
    informative_discussion: "informative",
    low_duplicate_share: "low dup",
    seed_linked: "seed+CA",
    catalyst: "catalyst",
    duplicate_text_cluster: "repeat",
    repeated_text_cluster: "repeat",
    low_information_posts: "meme only"
  };
  return labels[reason] ?? compactLabel(reason);
}

function drawerQualityLabel(item: TokenFlowItem): string {
  const label = qualityLabel(item);
  return label === "CA direct" ? "direct" : label;
}

export function tokenDrawerSummary(item: TokenFlowItem) {
  return {
    heat: `${formatScore(item.social_heat.score)} / ${compactLabel(item.social_heat.status)}`,
    quality: `${formatScore(item.discussion_quality.score)} / ${drawerQualityLabel(item)}`,
    spread: `${compactNumber(item.propagation.independent_authors)} authors`,
    timing: timingDrawerLabel(item)
  };
}

function propagationTitle(item: TokenFlowItem): string {
  return `${compactLabel(item.propagation.phase)} · ${compactNumber(item.propagation.independent_authors)} author`;
}

function propagationMeta(item: TokenFlowItem): string {
  return `top ${formatPercentShare(item.propagation.top_author_share)} · repro ${trimDecimal(item.propagation.reproduction_rate)}`;
}

function timingTitle(item: TokenFlowItem): string {
  const labels: Record<string, string> = {
    neutral: "neutral",
    market_pending: "market pending",
    market_unavailable: "market unavailable",
    chase_risk: "chase risk"
  };
  return labels[item.timing.status] ?? compactLabel(item.timing.status);
}

function timingDrawerLabel(item: TokenFlowItem): string {
  return timingTitle(item);
}

function timingMeta(item: TokenFlowItem): string {
  if (item.timing.status === "market_pending") {
    return "market observation pending";
  }
  if (item.timing.status === "market_unavailable") {
    return formatRisk(item.timing.market_observation_status ?? item.market.market_observation_status ?? item.timing.risks[0]);
  }
  if (item.timing.chase_risk || item.timing.status === "chase_risk") {
    return `${formatSignedPercent(item.timing.price_change_before_social_pct ?? item.market.price_change_before_social_pct)} before social`;
  }
  const risk = item.timing.risks[0] ?? item.timing.reasons[0];
  if (risk) {
    return formatRisk(risk);
  }
  const change = item.timing.price_change_since_social_pct ?? item.market.price_change_since_social_pct;
  if (change !== null && change !== undefined) {
    return `${formatSignedPercent(change)} since social`;
  }
  if (
    item.market.price_change_status &&
    item.market.price_change_status !== "ready" &&
    item.market.price_change_status !== "insufficient_history"
  ) {
    return formatRisk(item.market.price_change_status);
  }
  return item.market.market_status;
}

function scoreClass(score: number): string {
  if (score >= 82) return "score-hot";
  if (score >= 70) return "score-good";
  if (score >= 50) return "score-warn";
  return "score-risk";
}

function Barline({ score }: { score: number }) {
  const hotBars = Math.max(1, Math.min(8, Math.round(score / 12.5)));
  return (
    <div className="barline" aria-hidden>
      {Array.from({ length: 8 }, (_, index) => (
        <i className={index >= 8 - hotBars ? "hot" : ""} key={index} />
      ))}
    </div>
  );
}

function compactLabel(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "-";
}

function trimDecimal(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(1).replace(/\.0$/, "");
}
