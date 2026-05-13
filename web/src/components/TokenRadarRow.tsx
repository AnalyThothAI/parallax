import type { TokenFlowItem } from "@lib/types";
import { ArrowRight } from "lucide-react";

import { isDexMarket } from "../domain/tokenTarget";
import {
  compactNumber,
  formatPercentShare,
  formatRisk,
  formatScore,
  formatScoreDelta,
  formatSignedPercent,
  formatTokenPriceUsd,
  formatUsdCompact,
  shortAddress,
  tokenLabel,
} from "../lib/format";
import { tokenVenueAction } from "../lib/venue";

import { DecisionTag } from "./DecisionTag";
import { compactLabel, qualityLabel, timingTitle } from "./TokenRadarRow.model";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  onOpenSearch: (item: TokenFlowItem) => void;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({ item, selected, onOpenSearch, onSelect }: TokenRadarRowProps) {
  const delta = formatSignedPercent(
    item.market.price_change_since_social_pct ?? item.market.price_change_since_first_snapshot_pct,
  );
  const direction = delta.startsWith("+")
    ? "up"
    : delta !== "-" && delta.startsWith("-")
      ? "down"
      : "flat";
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
          <small className={`direction ${direction}`}>{marketMeta(item, delta)}</small>
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
          <a
            aria-label={`Open ${tokenLabel(item)} on ${venueAction.label}`}
            className="venue-link"
            href={venueAction.url}
            rel="noreferrer"
            target="_blank"
          >
            {venueAction.label}
          </a>
        ) : null}
        {!venueAction ? <span className="muted">-</span> : null}
        <button
          aria-label={`Open Search Intel for ${tokenLabel(item)}`}
          className="row-drilldown-button"
          title="Search Intel"
          type="button"
          onClick={() => onOpenSearch(item)}
        >
          <ArrowRight aria-hidden />
        </button>
      </span>
    </div>
  );
}

function heatTitle(item: TokenFlowItem): string {
  return `${formatScore(item.social_heat.score)} · ${compactNumber(item.social_heat.mentions)} ${formatScoreDelta(item.social_heat.mention_delta)}`;
}

function identitySubtitle(item: TokenFlowItem): string {
  if (item.identity.venue_type === "cex") {
    return (
      [item.identity.exchange?.toUpperCase(), item.identity.inst_id].filter(Boolean).join(" · ") ||
      "CEX"
    );
  }
  if (item.identity.address) {
    return `${item.identity.chain ?? "unknown"} · ${shortAddress(item.identity.address)}`;
  }
  if (item.identity.target_type && item.identity.target_id) {
    return item.identity.chain ? `${item.identity.chain} · resolved target` : "resolved target";
  }
  const reason = item.identity.resolution_reasons?.[0] ?? item.identity.identity_status;
  const candidateText = item.identity.candidate_count
    ? ` · ${compactNumber(item.identity.candidate_count)} candidates`
    : "";
  const discoveryText = item.identity.discovery_status
    ? ` · ${compactLabel(item.identity.discovery_status)}`
    : "";
  return `symbol-only · ${formatRisk(reason)}${candidateText}${discoveryText}`;
}

function marketPrimary(item: TokenFlowItem): string {
  if (isDexMarket(item)) {
    return item.market.market_cap !== null && item.market.market_cap !== undefined
      ? formatUsdCompact(item.market.market_cap)
      : "-";
  }
  if (item.market.market_cap !== null && item.market.market_cap !== undefined) {
    return formatUsdCompact(item.market.market_cap);
  }
  if (item.market.price !== null && item.market.price !== undefined) {
    return formatTokenPriceUsd(item.market.price);
  }
  return "-";
}

function marketMeta(item: TokenFlowItem, delta: string): string {
  const details = marketFreshnessDetails(item);
  const parts = [
    marketDeltaLabel(delta),
    marketStatusLabel(item.market.market_status),
    ...details,
  ].filter((part): part is string => Boolean(part));
  return parts.join(" · ");
}

function marketDeltaLabel(delta: string): string | null {
  return delta === "-" ? null : delta;
}

function marketStatusLabel(marketStatus: string): string | null {
  if (marketStatus === "live") {
    return "live";
  }
  if (marketStatus === "anchored" || marketStatus === "fresh" || marketStatus === "ready") {
    return null;
  }
  return compactLabel(marketStatus);
}

function marketFreshnessDetails(item: TokenFlowItem): string[] {
  const marketStatus = item.market.market_status;
  const details: string[] = [];
  if (!isDexMarket(item) && shouldShowFieldStatus(item.market.price_status, marketStatus)) {
    details.push(`price ${compactLabel(item.market.price_status)}`);
  }
  if (
    isDexMarket(item) &&
    (item.market.market_cap === null || item.market.market_cap === undefined) &&
    item.market.market_cap_status
  ) {
    details.push(`cap ${compactLabel(item.market.market_cap_status)}`);
  }
  if (
    item.market.market_cap !== null &&
    item.market.market_cap !== undefined &&
    shouldShowFieldStatus(item.market.market_cap_status, marketStatus)
  ) {
    details.push(`cap ${compactLabel(item.market.market_cap_status)}`);
  }
  if (
    item.market.liquidity !== null &&
    item.market.liquidity !== undefined &&
    shouldShowFieldStatus(item.market.liquidity_status, marketStatus)
  ) {
    details.push(`liq ${compactLabel(item.market.liquidity_status)}`);
  }
  return details;
}

function shouldShowFieldStatus(
  fieldStatus: string | null | undefined,
  marketStatus: string,
): boolean {
  if (!fieldStatus) {
    return false;
  }
  if (fieldStatus === marketStatus) {
    return false;
  }
  if (fieldStatus === "ready" || fieldStatus === "fresh" || fieldStatus === "live") {
    return false;
  }
  if (marketStatus === "missing" && fieldStatus === "missing") {
    return false;
  }
  return true;
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

function propagationTitle(item: TokenFlowItem): string {
  return `${compactLabel(item.propagation.phase)} · ${compactNumber(item.propagation.independent_authors)} author`;
}

function propagationMeta(item: TokenFlowItem): string {
  return `top ${formatPercentShare(item.propagation.top_author_share)} · repro ${trimDecimal(item.propagation.reproduction_rate)}`;
}

function timingMeta(item: TokenFlowItem): string {
  if (item.timing.status === "market_pending") {
    return "market observation pending";
  }
  if (item.timing.status === "market_unavailable") {
    return formatRisk(
      item.timing.market_observation_status ??
        item.market.market_observation_status ??
        item.timing.risks[0],
    );
  }
  if (item.timing.chase_risk || item.timing.status === "chase_risk") {
    return `${formatSignedPercent(item.timing.price_change_before_social_pct ?? item.market.price_change_before_social_pct)} before social`;
  }
  const risk = item.timing.risks[0] ?? item.timing.reasons[0];
  if (risk) {
    return formatRisk(risk);
  }
  const change =
    item.timing.price_change_since_social_pct ?? item.market.price_change_since_social_pct;
  if (change !== null && change !== undefined) {
    return `${formatSignedPercent(change)} since social`;
  }
  if (
    item.market.price_change_status &&
    item.market.price_change_status !== "ready" &&
    item.market.price_change_status !== "insufficient_history" &&
    item.market.price_change_status !== "live_not_persisted"
  ) {
    return formatRisk(item.market.price_change_status);
  }
  return marketStatusLabel(item.market.market_status) ?? "";
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

function trimDecimal(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(1).replace(/\.0$/, "");
}
