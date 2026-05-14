import type { TokenFlowItem } from "@lib/types";
import { buildTokenRadarCompactCase } from "@shared/model/tokenRadarCompactCase";
import { ObsidianPill, ObsidianTokenMark } from "@shared/ui/case-file";
import clsx from "clsx";
import { ArrowRight } from "lucide-react";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  onOpenSearch: (item: TokenFlowItem) => void;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({ item, selected, onOpenSearch, onSelect }: TokenRadarRowProps) {
  const tokenCase = buildTokenRadarCompactCase(item);

  return (
    <article className={clsx("radar-row", selected && "selected")}>
      <button
        aria-label={`Open token item ${tokenCase.label}`}
        className={clsx("radar-row-select", selected && "selected")}
        type="button"
        onClick={() => onSelect(item)}
      >
        <span className="radar-case-identity" data-case-section="identity">
          {tokenCase.logoUrl ? (
            <img alt="" className="radar-token-logo" src={tokenCase.logoUrl} />
          ) : (
            <ObsidianTokenMark label={tokenCase.label} tone={tokenCase.decision.tone} />
          )}
          <span>
            <span className="radar-case-symbol">
              <strong>{tokenCase.label}</strong>
              <ObsidianPill tone={tokenCase.trust.tone}>{tokenCase.trust.value}</ObsidianPill>
            </span>
            <span className="radar-case-meta">{tokenCase.subtitle}</span>
          </span>
        </span>

        <span className="radar-fact social-fact" data-case-section="social">
          <b>{tokenCase.socialFact}</b>
        </span>

        <span className="radar-fact narrative-fact" data-case-section="why-now">
          <ObsidianPill tone={tokenCase.narrative.tone}>{tokenCase.narrative.value}</ObsidianPill>
          <em>{tokenCase.narrative.detail}</em>
        </span>

        <span className="radar-fact market-fact" data-radar-metric="market">
          <b>{tokenCase.market.value}</b>
          <em>{tokenCase.market.detail}</em>
        </span>

        <span className="score-cell" data-case-section="action">
          <span className="score">{tokenCase.score}</span>
          <ObsidianPill tone={tokenCase.decision.tone}>{tokenCase.decision.value}</ObsidianPill>
        </span>
      </button>

      <span className="case-row-actions" data-radar-action="venue">
        {tokenCase.actions.venueHref ? (
          <a
            aria-label={`Open ${tokenCase.label} on ${tokenCase.actions.venueLabel}`}
            className="venue-link"
            href={tokenCase.actions.venueHref}
            rel="noreferrer"
            target="_blank"
          >
            {tokenCase.actions.venueLabel}
          </a>
        ) : null}
        {!tokenCase.actions.venueHref ? <span className="muted">-</span> : null}
        <button
          aria-label={`Open Search Intel for ${tokenCase.label}`}
          className="row-drilldown-button"
          title={tokenCase.actions.searchLabel}
          type="button"
          onClick={() => onOpenSearch(item)}
        >
          <span>{tokenCase.actions.searchLabel}</span>
          <ArrowRight aria-hidden />
        </button>
      </span>
    </article>
  );
}
