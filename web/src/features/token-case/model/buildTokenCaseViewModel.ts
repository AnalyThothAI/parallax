import { compactNumber, formatTokenPriceUsd, formatUsdCompact, shortAddress } from "@lib/format";
import type {
  NarrativeArgument,
  NarrativeCluster,
  TokenCaseDossier,
  TokenCasePostsData,
  TokenDiscussionDigest,
  TokenMentionSemantic,
  TokenPostItem,
} from "@lib/types";
import { narrativeGapLabels } from "@shared/model/narrativeDataGaps";
import type {
  TokenCaseMarketView,
  TokenCasePostEvent,
  TokenCaseTone,
  TokenCaseViewModel,
} from "@shared/model/tokenCaseViewModel";
import { tokenImageUrl } from "@shared/model/tokenImageUrl";
import {
  buildTokenPostEventMarket,
  cleanText,
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
  const digest = dossier.discussion_digest;
  const dataGaps = narrativeGapLabels(digest.data_gaps);
  const propagationState = digestPropagationState(digest) ?? dossier.timeline.summary.phase;

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
      logoUrl: tokenImageUrl(profileIdentity?.logo_url),
      title,
      subtitle: heroSubtitle(dossier, digest),
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
        value: phaseLabel(propagationState),
        detail: digest.coverage?.semantic_coverage
          ? `${Math.round(digest.coverage.semantic_coverage * 100)}% semantic coverage`
          : "semantic coverage pending",
        tone: phaseTone(propagationState),
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
      summaryZh: propagationSummary(digest),
      statusPills: digestStatusPills(digest),
      stages: digestStages(dossier.narrative_clusters, digest),
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
      stance: digest.bull_bear?.stance ?? digest.status,
      bull: {
        title: "Bull · 多头",
        thesis: digest.bull_bear?.bull.thesis_zh ?? "",
        evidenceEventIds: evidenceEventIds(digest.bull_bear?.bull.evidence_refs),
        bullets: digest.bull_bear?.bull.bullets_zh ?? [],
        tone: "health",
      },
      bear: {
        title: "Bear · 空头",
        thesis: digest.bull_bear?.bear.thesis_zh ?? "",
        evidenceEventIds: evidenceEventIds(digest.bull_bear?.bear.evidence_refs),
        bullets: digest.bull_bear?.bear.bullets_zh ?? [],
        tone: "risk",
      },
    },
    amplifiers: digestAmplifiers(digest, dossier.narrative_clusters).map((account) => ({
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
  const semantic = post.semantic ?? null;
  return {
    id: post.event_id,
    handle: cleanText(post.handle ?? post.author_role),
    text: cleanText(post.text) ?? "(empty post)",
    url: cleanText(post.url),
    timestampMs: post.received_at_ms ?? null,
    timeLabel: post.received_at_ms ? timeAgoLabel(post.received_at_ms) : null,
    phase:
      cleanText(semantic?.narrative_cluster_title) ?? cleanText(semantic?.narrative_cluster_key),
    role: semanticRole(semantic),
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
  const pricePill = tokenPricePill(post.price?.price_usd, post.price?.status);
  if (pricePill) {
    pills.push(pricePill);
  }
  const semantic = post.semantic;
  if (!semantic) {
    pills.push({ label: "semantic unavailable", tone: "warn" });
    return pills;
  }
  if (semantic.status !== "ready" && semantic.status !== "labeled") {
    pills.push({
      label: semantic.status.replaceAll("_", " "),
      tone: semanticStatusTone(semantic.status),
    });
    return pills;
  }
  const stance = cleanText(semantic.trade_stance);
  if (stance && stance !== "unknown") {
    pills.push({ label: stance, tone: stanceTone(stance) });
  }
  const valence = cleanText(semantic.attention_valence);
  if (valence && valence !== "unknown") {
    pills.push({ label: valence, tone: valenceTone(valence) });
  }
  const cluster =
    cleanText(semantic.narrative_cluster_title) ?? cleanText(semantic.narrative_cluster_key);
  if (cluster) {
    pills.push({ label: cluster, tone: "info" });
  }
  return pills;
}

function heroSubtitle(dossier: TokenCaseDossier, digest: TokenDiscussionDigest): string {
  const narrativeTitle = cleanText(digest.dominant_narrative?.title);
  if (digest.status === "ready" && narrativeTitle) {
    return narrativeTitle;
  }
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

function phaseLabel(value?: string | null): string {
  const text = cleanText(value) ?? "unknown";
  return text.replaceAll("_", " ");
}

function digestPropagationState(digest: TokenDiscussionDigest): string | null {
  return (
    cleanText(digest.propagation?.state) ??
    cleanText(digest.dominant_narrative?.propagation_state) ??
    null
  );
}

function propagationSummary(digest: TokenDiscussionDigest): string {
  return (
    cleanText(digest.propagation?.summary_zh) ??
    cleanText(digest.dominant_narrative?.summary_zh) ??
    digestStatusLabel(digest.status)
  );
}

function digestStatusPills(
  digest: TokenDiscussionDigest,
): Array<{ label: string; tone: TokenCaseTone }> {
  const pills: Array<{ label: string; tone: TokenCaseTone }> = [
    { label: digestStatusLabel(digest.status), tone: digestStatusTone(digest.status) },
  ];
  const state = digestPropagationState(digest);
  if (state) {
    pills.push({ label: phaseLabel(state), tone: phaseTone(state) });
  }
  const topStance = topMixLabel(digest.stance_mix);
  if (topStance) {
    pills.push({ label: topStance, tone: "info" });
  }
  const coverage = digest.coverage?.semantic_coverage;
  if (typeof coverage === "number" && Number.isFinite(coverage)) {
    pills.push({ label: `${Math.round(coverage * 100)}% coverage`, tone: "neutral" });
  }
  return pills;
}

function digestStages(
  clusters: NarrativeCluster[],
  digest: TokenDiscussionDigest,
): TokenCaseViewModel["propagation"]["stages"] {
  const fromClusters = clusters.slice(0, 3).map((cluster) => {
    const state = cluster.propagation_state ?? digestPropagationState(digest) ?? cluster.cluster_key;
    const lead = cluster.lead_accounts?.[0]?.handle;
    return {
      id: cluster.cluster_key,
      phase: phaseLabel(state),
      count: cluster.mention_count ?? 0,
      authors: cluster.author_count ?? 0,
      leadAccount: lead ? `@${lead.replace(/^@+/, "")}` : null,
      readZh: cluster.summary_zh,
      tone: phaseTone(state),
    };
  });
  if (fromClusters.length) {
    return fromClusters;
  }
  const state = digestPropagationState(digest) ?? digest.status;
  return [
    {
      id: "digest",
      phase: phaseLabel(state),
      count: digest.coverage?.source_mentions ?? 0,
      authors: digest.coverage?.independent_authors ?? 0,
      leadAccount: null,
      readZh: propagationSummary(digest),
      tone: phaseTone(state),
    },
  ];
}

function digestAmplifiers(digest: TokenDiscussionDigest, clusters: NarrativeCluster[]) {
  if (digest.key_accounts?.length) {
    return digest.key_accounts;
  }
  return clusters.flatMap((cluster) =>
    (cluster.lead_accounts ?? []).map((account) => ({
      handle: account.handle,
      role: account.role ?? cluster.title,
      posts: account.posts ?? 0,
      first_seen_ms: account.first_seen_ms,
    })),
  );
}

function topMixLabel(mix: TokenDiscussionDigest["stance_mix"]): string | null {
  const top = Object.entries(mix ?? {})
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => Number(right[1]) - Number(left[1]))[0];
  return top ? `${top[0]} ${Math.round(Number(top[1]) * 100)}%` : null;
}

function digestStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    insufficient: "insufficient",
    pending: "pending",
    ready: "ready",
    semantic_unavailable: "semantic unavailable",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function digestStatusTone(status: string): TokenCaseTone {
  if (status === "ready") return "health";
  if (status === "pending") return "info";
  return "warn";
}

function semanticRole(semantic: TokenMentionSemantic | null): string | null {
  return (
    cleanText(semantic?.claim_type) ??
    cleanText(semantic?.evidence_type) ??
    cleanText(semantic?.status) ??
    null
  );
}

function semanticStatusTone(status: string): TokenCaseTone {
  if (status === "pending" || status === "queued") return "info";
  return "warn";
}

function stanceTone(stance: string): TokenCaseTone {
  if (stance === "bullish") return "health";
  if (stance === "bearish" || stance === "exit-risk") return "risk";
  if (stance === "skeptical") return "warn";
  return "neutral";
}

function valenceTone(valence: string): TokenCaseTone {
  if (valence === "positive" || valence === "celebratory") return "health";
  if (valence === "panic" || valence === "hostile" || valence === "negative") return "risk";
  if (valence === "mixed" || valence === "ironic") return "warn";
  return "info";
}

function evidenceEventIds(refs: NarrativeArgument["evidence_refs"] | undefined): string[] {
  return (refs ?? [])
    .map((ref) => cleanText(ref.event_id))
    .filter((eventId): eventId is string => Boolean(eventId));
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
