import { formatRisk, formatScore, formatSignedPercent, tokenLabel } from "@lib/format";
import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type { TokenFlowItem, TokenSocialTimelineData, WindowKey } from "@lib/types";
import { buildTokenCaseView } from "@shared/model/tokenCase";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import {
  ObsidianActionBar,
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianFieldGrid,
  ObsidianPill,
  ObsidianTokenMark,
} from "@shared/ui/case-file";
import { ArrowLeft, ExternalLink, Search } from "lucide-react";
import { Link } from "react-router-dom";

type TokenTargetCaseSummaryProps = {
  token: TokenFlowItem;
  timeline: TokenSocialTimelineData | null;
  windowKey: WindowKey;
  onBack: () => void;
  onWindowChange: (window: WindowKey) => void;
};

export function TokenTargetCaseSummary({
  token,
  timeline,
  windowKey,
  onBack,
  onWindowChange,
}: TokenTargetCaseSummaryProps) {
  const tokenCase = buildTokenCaseView(token);
  const riskLead =
    token.opportunity.hard_risks?.[0] ?? token.opportunity.risks[0] ?? token.timing.risks[0];
  const socialDetail =
    timeline?.summary.posts !== undefined && timeline?.summary.authors !== undefined
      ? `${timeline.summary.posts} posts · ${timeline.summary.authors} authors in timeline`
      : tokenCase.community.detail;

  return (
    <ObsidianCase aria-label={`Token item ${tokenCase.label}`} className="token-target-case">
      <ObsidianCaseHeader
        actions={
          <TokenTargetActions
            searchHref={tokenCase.actions.searchHref}
            searchLabel={tokenCase.actions.searchLabel}
            venueHref={tokenCase.actions.venueHref}
            venueLabel={tokenCase.actions.venueLabel}
            windowKey={windowKey}
            onBack={onBack}
            onWindowChange={onWindowChange}
          />
        }
        badge={
          <ObsidianPill tone={tokenCase.decision.tone}>{tokenCase.decision.value}</ObsidianPill>
        }
        eyebrow="token item"
        lead={<TokenProfileCard profile={token.profile} />}
        mark={<ObsidianTokenMark label={tokenCase.label} tone={tokenCase.decision.tone} />}
        meta={
          <span className="token-target-score">score {formatScore(token.opportunity.score)}</span>
        }
        subtitle={tokenCase.subtitle}
        title={tokenLabel(token)}
      />

      <ObsidianFieldGrid
        fields={[
          tokenCase.official,
          { ...tokenCase.community, detail: socialDetail },
          tokenCase.narrative,
          tokenCase.market,
          {
            detail: token.market.price_at_social_start
              ? `from ${token.market.price_at_social_start}`
              : "social anchor pending",
            label: "Since social",
            source: "market",
            tone: deltaTone(token.market.price_change_since_social_pct),
            value: formatSignedPercent(token.market.price_change_since_social_pct),
          },
          {
            detail: token.flow.baseline_status,
            label: "Risk flag",
            source: "deterministic",
            tone: riskLead ? "risk" : "health",
            value: riskLead ? formatRisk(riskLead) : "clear",
          },
        ]}
      />
    </ObsidianCase>
  );
}

function TokenTargetActions({
  searchHref,
  searchLabel,
  venueHref,
  venueLabel,
  windowKey,
  onBack,
  onWindowChange,
}: {
  searchHref: string;
  searchLabel: string;
  venueHref?: string;
  venueLabel?: string;
  windowKey: WindowKey;
  onBack: () => void;
  onWindowChange: (window: WindowKey) => void;
}) {
  return (
    <div className="token-target-actions">
      <button
        className="ghost-icon-button"
        type="button"
        onClick={onBack}
        aria-label="Back to Radar"
      >
        <ArrowLeft aria-hidden />
        <span>Radar</span>
      </button>
      <div className="segmented mini range" aria-label="audit page window">
        {OBSERVATION_WINDOWS.map((item) => (
          <button
            key={item}
            className={windowKey === item ? "active" : ""}
            type="button"
            onClick={() => onWindowChange(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <ObsidianActionBar className="token-target-links">
        <Link aria-label={searchLabel} to={searchHref}>
          <Search aria-hidden />
          <span>{searchLabel}</span>
        </Link>
        {venueHref ? (
          <a
            aria-label={`Open token on ${venueLabel}`}
            href={venueHref}
            rel="noreferrer"
            target="_blank"
          >
            <ExternalLink aria-hidden />
            <span>{venueLabel}</span>
          </a>
        ) : null}
      </ObsidianActionBar>
    </div>
  );
}

function deltaTone(value?: number | null) {
  if (value === null || value === undefined) {
    return "neutral";
  }
  return value >= 0 ? "health" : "risk";
}
