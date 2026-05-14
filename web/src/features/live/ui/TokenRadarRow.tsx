import type { TokenFlowItem } from "@lib/types";
import { buildTokenCaseView } from "@shared/model/tokenCase";
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
  const tokenCase = buildTokenCaseView(item);

  return (
    <article className={clsx("radar-row", selected && "selected")}>
      <button
        aria-label={`Open token item ${tokenCase.label}`}
        className={clsx("radar-row-select", selected && "selected")}
        type="button"
        onClick={() => onSelect(item)}
      >
        <span className="radar-case-identity" data-case-section="identity">
          <ObsidianTokenMark label={tokenCase.label} tone={tokenCase.decision.tone} />
          <span>
            <span className="radar-case-kicker">Identity</span>
            <span className="radar-case-symbol">
              <strong>{tokenCase.label}</strong>
              <ObsidianPill tone={tokenCase.official.tone}>
                {officialStatus(tokenCase)}
              </ObsidianPill>
            </span>
            <span className="radar-case-meta">{tokenCase.identity.detail}</span>
            <span className="radar-case-micro">
              <span data-radar-metric="market">
                {tokenCase.market.value}
                <em>{tokenCase.market.detail}</em>
              </span>
              <span>{tokenCase.actions.venueLabel ?? "venue pending"}</span>
            </span>
          </span>
        </span>

        <span className="case-cell" data-case-section="official">
          <small>Official</small>
          <b>{tokenCase.official.value}</b>
          <em>{tokenCase.official.detail}</em>
        </span>

        <span className="case-cell community-cell" data-case-section="community">
          <small>{tokenCase.community.label}</small>
          <b>{tokenCase.community.value}</b>
          <em>{tokenCase.community.detail}</em>
        </span>

        <span className="case-cell narrative-cell" data-case-section="narrative">
          <small>{tokenCase.narrative.label}</small>
          <b>{tokenCase.narrative.value}</b>
          <em>{tokenCase.narrative.detail}</em>
        </span>

        <span className="score-cell" data-case-section="decision">
          <small>Decision</small>
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
          <ArrowRight aria-hidden />
        </button>
      </span>
    </article>
  );
}

function officialStatus(tokenCase: ReturnType<typeof buildTokenCaseView>): string {
  if (tokenCase.official.tone === "info" || tokenCase.official.tone === "health") {
    return "verified";
  }
  return tokenCase.identity.source === "deterministic" ? "resolved" : "partial";
}
