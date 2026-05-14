import type { TokenFlowItem } from "@lib/types";
import { buildTokenRadarCompactCase } from "@shared/model/tokenRadarCompactCase";
import { ObsidianTokenMark } from "@shared/ui/case-file";
import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, ExternalLink, Minus } from "lucide-react";

type TokenRadarRowProps = {
  item: TokenFlowItem;
  selected: boolean;
  onOpenSearch: (item: TokenFlowItem) => void;
  onSelect: (item: TokenFlowItem) => void;
};

export function TokenRadarRow({ item, selected, onOpenSearch, onSelect }: TokenRadarRowProps) {
  const tokenCase = buildTokenRadarCompactCase(item);
  const selectItem = () => onSelect(item);

  return (
    <article
      aria-label={`Token Radar item ${tokenCase.label}`}
      className={clsx("token-radar-row", selected && "selected")}
    >
      <div className="radar-case-cell" data-case-section="identity">
        {tokenCase.logoUrl ? (
          <img alt="" className="radar-token-logo" src={tokenCase.logoUrl} />
        ) : (
          <ObsidianTokenMark label={tokenCase.label} tone={tokenCase.markTone} />
        )}
        <span className="radar-case-copy">
          <span className="radar-case-symbol-row">
            <button
              aria-label={`Open token item ${tokenCase.label}`}
              className={clsx("radar-case-button", selected && "selected")}
              type="button"
              onClick={selectItem}
            >
              <strong>{tokenCase.label}</strong>
            </button>
            {tokenCase.externalLinks.length ? (
              <nav
                className="radar-case-links"
                aria-label={`External links for ${tokenCase.label}`}
              >
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
          </span>
          <span className="radar-case-meta">{tokenCase.subtitle}</span>
        </span>
      </div>

      <span className="radar-fact social-fact" data-case-section="social">
        <b>{tokenCase.socialFact}</b>
        <em>{tokenCase.socialDetail}</em>
      </span>

      <span className="radar-fact narrative-fact" data-case-section="why-now">
        <b>{tokenCase.narrative.value}</b>
        <em>{tokenCase.narrative.detail}</em>
      </span>

      <span className="radar-fact market-fact" data-radar-metric="market">
        <span className="market-primary-line">
          <b className="market-primary-value">{tokenCase.market.value}</b>
          <span className={clsx("market-move", tokenCase.marketMove.direction)}>
            {tokenCase.marketMove.direction === "up" ? <ArrowUpRight aria-hidden /> : null}
            {tokenCase.marketMove.direction === "down" ? <ArrowDownRight aria-hidden /> : null}
            {tokenCase.marketMove.direction === "flat" ? <Minus aria-hidden /> : null}
            <b>{tokenCase.marketMove.value}</b>
          </span>
        </span>
        <span className="market-stats" aria-label={tokenCase.market.detail}>
          {tokenCase.market.stats.length ? (
            tokenCase.market.stats.map((stat) => (
              <span className={clsx("market-stat", stat.tone)} key={stat.key} title={stat.status}>
                <span>{stat.label}</span>
                <b>{stat.value}</b>
              </span>
            ))
          ) : (
            <em>market data unavailable</em>
          )}
        </span>
      </span>

      <span className="radar-fact listed-fact" data-radar-metric="listed">
        <b>{tokenCase.listed.value}</b>
        <em>{tokenCase.listed.detail}</em>
      </span>

      <span className="radar-score-cell" data-case-section="action">
        <span className="radar-score">{tokenCase.score}</span>
        <button
          aria-label={`Open Search Intel for ${tokenCase.label}`}
          className="row-drilldown-button"
          title={tokenCase.searchTitle}
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpenSearch(item);
          }}
        >
          <ExternalLink aria-hidden />
        </button>
      </span>
    </article>
  );
}
