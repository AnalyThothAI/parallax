import type { TokenFlowItem } from "@lib/types";
import { buildTokenRadarCompactCase } from "@shared/model/tokenRadarCompactCase";
import { ObsidianTokenMark } from "@shared/ui/case-file";
import clsx from "clsx";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from "lucide-react";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  onOpenSearch: (item: TokenFlowItem) => void;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({ item, selected, onOpenSearch, onSelect }: TokenRadarRowProps) {
  const tokenCase = buildTokenRadarCompactCase(item);

  return (
    <article
      aria-label={`Token Radar item ${tokenCase.label}`}
      className={clsx("radar-row", selected && "selected")}
    >
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
            <ObsidianTokenMark label={tokenCase.label} tone={tokenCase.markTone} />
          )}
          <span>
            <span className="radar-case-symbol">
              <strong>{tokenCase.label}</strong>
            </span>
            <span className="radar-case-meta">{tokenCase.subtitle}</span>
          </span>
        </span>

        <span className="radar-fact social-fact" data-case-section="social">
          <b>{tokenCase.socialFact}</b>
          <em>{tokenCase.socialDetail}</em>
        </span>

        <span className="radar-fact narrative-fact" data-case-section="why-now">
          <b>{tokenCase.narrative.value}</b>
          <em>{tokenCase.narrative.detail}</em>
        </span>

        <span className="radar-fact market-fact" data-radar-metric="market">
          <span>
            <b>{tokenCase.market.value}</b>
            <em>{tokenCase.market.detail}</em>
          </span>
          <span className={clsx("market-move", tokenCase.marketMove.direction)}>
            {tokenCase.marketMove.direction === "up" ? <ArrowUpRight aria-hidden /> : null}
            {tokenCase.marketMove.direction === "down" ? <ArrowDownRight aria-hidden /> : null}
            {tokenCase.marketMove.direction === "flat" ? <Minus aria-hidden /> : null}
            <b>{tokenCase.marketMove.value}</b>
          </span>
        </span>
      </button>

      {tokenCase.externalLinks.length ? (
        <nav className="radar-case-links" aria-label={`External links for ${tokenCase.label}`}>
          {tokenCase.externalLinks.map((link) => (
            <a
              className={clsx("radar-case-link", link.tone)}
              href={link.href}
              key={`${link.label}:${link.href}`}
              rel="noreferrer"
              target="_blank"
            >
              {link.label}
            </a>
          ))}
        </nav>
      ) : null}

      <span className="score-cell" data-case-section="action">
        <span className="score">{tokenCase.score}</span>
        <button
          aria-label={`Open Search Intel for ${tokenCase.label}`}
          className="row-drilldown-button"
          title={tokenCase.searchTitle}
          type="button"
          onClick={() => onOpenSearch(item)}
        >
          <ArrowRight aria-hidden />
        </button>
      </span>
    </article>
  );
}
