import { compactNumber, formatRisk } from "@lib/format";
import type { TokenFlowItem } from "@lib/types";

import { buildTokenCaseView, type TokenCaseTone } from "./tokenCase";

export type TokenRadarCompactCase = ReturnType<typeof buildTokenRadarCompactCase>;

export function buildTokenRadarCompactCase(item: TokenFlowItem) {
  const tokenCase = buildTokenCaseView(item);
  const profile = item.profile;
  const links = profile?.links;
  const hasProfile = profile?.status === "ready";
  const hasLinks = Boolean(
    links?.website_url ||
    links?.twitter_url ||
    links?.twitter_username ||
    links?.telegram_url ||
    links?.gmgn_url ||
    links?.geckoterminal_url,
  );
  const risk = compactRisk(item);
  const trustTone: TokenCaseTone = hasProfile ? "info" : hasLinks ? "health" : "neutral";

  return {
    actions: tokenCase.actions,
    decision: tokenCase.decision,
    label: tokenCase.label,
    logoUrl: profile?.identity?.logo_url ?? null,
    market: tokenCase.market,
    narrative: {
      detail: tokenCase.narrative.detail,
      tone: risk ? "risk" : tokenCase.narrative.tone,
      value: risk ?? tokenCase.narrative.value,
    },
    score: tokenCase.score,
    socialFact: `${compactNumber(item.flow.mentions)} posts · ${compactNumber(
      item.propagation.independent_authors,
    )} authors · ${compactNumber(item.flow.watched_mentions)} watched`,
    subtitle: tokenCase.subtitle,
    trust: {
      tone: trustTone,
      value: hasProfile ? "profile" : hasLinks ? "links" : "unverified",
    },
  };
}

function compactRisk(item: TokenFlowItem): string | null {
  const risk =
    item.tradeability.risks[0] ??
    item.timing.risks[0] ??
    item.discussion_quality.risks[0] ??
    item.propagation.risks[0] ??
    item.opportunity.risks[0];
  return risk ? formatRisk(risk) : null;
}
