import { compactNumber, formatTokenPriceUsd, formatUsdCompact, shortAddress } from "@lib/format";
import type { TokenCaseDossier, TokenCasePostsData, TokenPostItem } from "@lib/types";
import type {
  TokenCaseMarketView,
  TokenCasePostEvent,
  TokenCaseTone,
  TokenCaseViewModel,
} from "@shared/model/tokenCaseViewModel";
import {
  buildTokenPostEventMarket,
  cleanText,
  normalizeTokenSymbol,
  numberValue,
  relativeTimeLabel,
  tokenPricePill,
} from "@shared/model/tokenPostEvent";

import type { TokenCaseRouteState } from "../state/tokenCaseRouteState";

export type BuildTokenCaseViewModelArgs = {
  dossier: TokenCaseDossier;
  route: TokenCaseRouteState;
  posts?: TokenCasePostsData | null;
  isLoadingPosts?: boolean;
  isFetchingNextPage?: boolean;
};

export function buildTokenCaseViewModel({
  dossier,
  route,
  posts,
  isLoadingPosts = false,
  isFetchingNextPage = false,
}: BuildTokenCaseViewModelArgs): TokenCaseViewModel {
  const target = dossier.target;
  const profileIdentity = dossier.profile?.identity;
  const symbol = cleanText(profileIdentity?.symbol) ?? cleanText(target.symbol);
  const name = cleanText(profileIdentity?.name);
  const title = symbol
    ? `$${symbol}${name && name !== symbol ? ` · ${name}` : ""}`
    : shortId(target.target_id);
  const mergedPosts = posts ?? dossier.posts;
  const market = buildMarketView(dossier);
  const livePrice = numberValue(dossier.market_live.price_usd);
  const timelineItems = sortTimelineItems(
    mergedPosts.items.map((post) => buildPostEvent(post, livePrice)),
    route.postSort,
  );
  const visibleTimelineItems =
    route.postSort === "watched" ? timelineItems.filter((item) => item.isWatched) : timelineItems;
  const dataGaps = dossier.agent_brief.project_summary.data_gaps.filter(Boolean);

  return {
    target: {
      targetType: target.target_type,
      targetId: target.target_id,
      symbol,
      name,
      chainId: cleanText(target.chain_id),
      address: cleanText(target.address),
      displayTitle: title,
      shortId: shortId(target.target_id),
    },
    route: {
      window: route.window,
      scope: route.scope,
      searchHref: `/search?q=${encodeURIComponent(symbol ? `$${symbol}` : target.target_id)}`,
    },
    hero: {
      logoUrl: cleanText(profileIdentity?.logo_url),
      title,
      subtitle: heroSubtitle(dossier),
      contractLabel: target.address
        ? `${target.chain_id ?? "chain"} · ${shortAddress(target.address)}`
        : null,
      actions: heroActions(dossier),
    },
    metrics: [
      {
        key: "mentions",
        label: "mentions",
        value: compactNumber(dossier.timeline.summary.posts),
        detail: `${compactNumber(dossier.timeline.summary.authors)} authors`,
        tone: dossier.timeline.summary.posts > 0 ? "health" : "neutral",
      },
      {
        key: "phase",
        label: "phase",
        value: phaseLabel(dossier.timeline.summary.phase),
        detail: `${dossier.timeline.stages.length} propagation stages`,
        tone: phaseTone(dossier.timeline.summary.phase),
      },
      {
        key: "watched",
        label: "watched",
        value: compactNumber(dossier.timeline.summary.watched_posts ?? 0),
        detail: route.scope === "watched" ? "watched-only route" : "all public mentions",
        tone: (dossier.timeline.summary.watched_posts ?? 0) > 0 ? "health" : "risk",
      },
      {
        key: "readiness",
        label: "readiness",
        value: market.status,
        detail: dataGaps.length ? `${dataGaps.length} data gaps` : "no reported gaps",
        tone: market.tone,
      },
    ],
    propagation: {
      summaryZh: dossier.agent_brief.propagation.summary_zh,
      statusPills: [
        {
          label: dossier.agent_brief.project_summary.current_state,
          tone: phaseTone(dossier.timeline.summary.phase),
        },
        {
          label: `${compactNumber(dossier.timeline.summary.effective_authors)} effective authors`,
          tone: "info",
        },
        {
          label: `top ${Math.round(dossier.timeline.summary.top_author_share * 100)}%`,
          tone: "neutral",
        },
      ],
      stages: dossier.agent_brief.propagation.phases.slice(0, 3).map((phase, index) => {
        const stage = dossier.timeline.stages[index];
        return {
          id: stage?.stage_id ?? `${phase.phase}-${index}`,
          phase: phaseLabel(phase.phase),
          count: stage?.people.posts ?? phase.tweets,
          authors: stage?.people.authors ?? phase.authors,
          leadAccount: phase.lead_accounts[0]
            ? `@${phase.lead_accounts[0].replace(/^@+/, "")}`
            : null,
          readZh: phase.read_zh,
          tone: phaseTone(phase.phase),
        };
      }),
    },
    timeline: {
      sort: route.postSort,
      items: visibleTimelineItems,
      hasMore: mergedPosts.has_more,
      isLoading: isLoadingPosts,
      isFetchingNextPage,
      emptyLabel: visibleTimelineItems.length ? null : "No matching posts in this window.",
    },
    market,
    bullBear: {
      stance: dossier.agent_brief.bull_bear.stance,
      bull: {
        title: "Bull · 多头",
        thesis: dossier.agent_brief.bull_bear.bull.thesis_zh,
        evidenceEventIds: dossier.agent_brief.bull_bear.bull.evidence_event_ids,
        bullets: dossier.agent_brief.bull_bear.bull.triggers_zh,
        tone: "health",
      },
      bear: {
        title: "Bear · 空头",
        thesis: dossier.agent_brief.bull_bear.bear.thesis_zh,
        evidenceEventIds: dossier.agent_brief.bull_bear.bear.evidence_event_ids,
        bullets: dossier.agent_brief.bull_bear.bear.invalidations_zh,
        tone: "risk",
      },
    },
    amplifiers: dossier.agent_brief.propagation.key_accounts.map((account) => ({
      handle: `@${account.handle.replace(/^@+/, "")}`,
      role: account.role,
      posts: account.posts,
      firstSeenLabel: account.first_seen_ms ? timeAgoLabel(account.first_seen_ms) : null,
    })),
    dataGaps,
  };
}

function buildPostEvent(post: TokenPostItem, livePriceUsd: number | null): TokenCasePostEvent {
  const score = numberValue(post.post_quality.score);
  const reasons = post.post_quality.reasons ?? [];
  return {
    id: post.event_id,
    handle: cleanText(post.handle ?? post.author_role),
    text: cleanText(post.text) ?? "(empty post)",
    url: cleanText(post.url),
    timestampMs: post.received_at_ms ?? null,
    timeLabel: post.received_at_ms ? timeAgoLabel(post.received_at_ms) : null,
    phase: cleanText(post.stage_phase),
    role: cleanText(post.author_role),
    isWatched: Boolean(post.is_watched),
    pills: postPills(post),
    market: buildPostMarket(post, livePriceUsd),
    quality: {
      score,
      scoreLabel: score === null ? "PQ -" : `PQ ${Math.round(score)}`,
      reasons,
      contributions: post.post_quality.contributions.slice(0, 3).map((contribution) => ({
        label: contribution.feature.replaceAll("_", " "),
        value: formatContributionValue(contribution.value),
        reason: contribution.reason,
      })),
    },
  };
}

function buildMarketView(dossier: TokenCaseDossier): TokenCaseMarketView {
  const live = dossier.market_live;
  const status = stringValue(live.status) ?? "missing";
  const price = numberValue(live.price_usd);
  const marketCap = numberValue(live.market_cap_usd);
  const liquidity = numberValue(live.liquidity_usd);
  const holders = numberValue(live.holders);
  const volume24h = numberValue(live.volume_24h_usd);
  const ready = status === "ready" || status === "live";
  return {
    status,
    provider: stringValue(live.provider),
    priceLabel: price === null ? "-" : formatTokenPriceUsd(price),
    marketCapLabel: marketCap === null ? "-" : formatUsdCompact(marketCap),
    liquidityLabel: liquidity === null ? "-" : formatUsdCompact(liquidity),
    holdersLabel: holders === null ? "-" : compactNumber(holders),
    volume24hLabel: volume24h === null ? "-" : formatUsdCompact(volume24h),
    observedAtLabel: numberValue(live.observed_at_ms)
      ? timeAgoLabel(Number(live.observed_at_ms))
      : null,
    emptyTitle: ready ? null : status === "stale" ? "Live market stale" : "Live market unavailable",
    emptyDetail: ready
      ? null
      : (stringValue(live.error) ??
        "No live market snapshot has been attached to this dossier yet."),
    tone: ready ? "health" : "warn",
  };
}

function buildPostMarket(
  post: TokenPostItem,
  livePriceUsd: number | null,
): TokenCasePostEvent["market"] {
  return buildTokenPostEventMarket({
    livePriceUsd,
    observationKind: post.price?.observation_kind,
    priceUsd: post.price?.price_usd,
    provider: post.price?.provider,
    status: post.price?.status,
  });
}

function sortTimelineItems(
  items: TokenCasePostEvent[],
  sort: TokenCaseRouteState["postSort"],
): TokenCasePostEvent[] {
  if (sort === "catalyst") {
    return [...items].sort(
      (left, right) => (right.quality.score ?? -1) - (left.quality.score ?? -1),
    );
  }
  return items;
}

function postPills(post: TokenPostItem): Array<{ label: string; tone: TokenCaseTone }> {
  const pills: Array<{ label: string; tone: TokenCaseTone }> = [];
  const symbol = normalizeTokenSymbol(post.symbol);
  if (symbol) {
    pills.push({ label: `$${symbol}`, tone: "opportunity" });
  }
  const pricePill = tokenPricePill(post.price?.price_usd, post.price?.status);
  if (pricePill) {
    pills.push(pricePill);
  }
  const score = numberValue(post.post_quality.score);
  pills.push({
    label: score === null ? "PQ -" : `PQ ${Math.round(score)}`,
    tone: scoreTone(score),
  });
  if (post.attribution_status) {
    pills.push({ label: post.attribution_status.replaceAll("_", " "), tone: "info" });
  }
  if (post.mention_source) {
    pills.push({ label: post.mention_source.replaceAll("_", " "), tone: "neutral" });
  }
  if (post.is_watched) {
    pills.push({ label: "watched", tone: "health" });
  }
  return pills;
}

function heroSubtitle(dossier: TokenCaseDossier): string {
  const target = dossier.target;
  const parts = [
    target.chain_id,
    target.address ? shortAddress(target.address) : null,
    dossier.profile?.status ? `profile ${dossier.profile.status}` : null,
  ].filter((part): part is string => Boolean(part));
  return parts.join(" · ") || target.target_id;
}

function heroActions(dossier: TokenCaseDossier): TokenCaseViewModel["hero"]["actions"] {
  const actions: TokenCaseViewModel["hero"]["actions"] = [];
  const twitter = cleanText(dossier.profile?.links?.twitter_username);
  const website = cleanText(dossier.profile?.links?.website_url);
  const gmgn = cleanText(dossier.profile?.links?.gmgn_url);
  if (twitter) {
    actions.push({
      label: "X",
      href: `https://x.com/${twitter.replace(/^@+/, "")}`,
      tone: "info",
    });
  }
  if (website) {
    actions.push({ label: "Website", href: website, tone: "neutral" });
  }
  if (gmgn) {
    actions.push({ label: "GMGN", href: gmgn, tone: "opportunity" });
  }
  return actions;
}

function phaseTone(phase?: string | null): TokenCaseTone {
  const normalized = phase?.toLowerCase();
  if (normalized === "expansion" || normalized === "escalation") {
    return "health";
  }
  if (normalized === "ignition") {
    return "opportunity";
  }
  if (normalized === "fade") {
    return "warn";
  }
  return "info";
}

function scoreTone(score: number | null): TokenCaseTone {
  if (score === null) return "neutral";
  if (score >= 80) return "health";
  if (score >= 60) return "info";
  return "warn";
}

function phaseLabel(value?: string | null): string {
  const text = cleanText(value) ?? "unknown";
  return text.replaceAll("_", " ");
}

function shortId(value: string): string {
  return value.length > 30 ? `${value.slice(0, 14)}...${value.slice(-8)}` : value;
}

function timeAgoLabel(timestampMs: number): string {
  return relativeTimeLabel(timestampMs);
}

function formatContributionValue(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
