import { compactNumber, formatTokenPriceUsd, formatUsdCompact, shortAddress } from "@lib/format";
import type {
  CexDetailSnapshot,
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
  TokenCaseMetric,
  TokenCasePostEvent,
  TokenCaseTone,
  TokenCaseViewModel,
} from "@shared/model/tokenCaseViewModel";
import {
  buildTokenPostEventMarket,
  cleanText,
  numberValue,
  relativeTimeLabel,
  tokenPricePill,
} from "@shared/model/tokenPostEvent";

import type { TokenCaseRouteState } from "../state/tokenCaseRouteState";

const LOCAL_LOGO_PREFIX = "/api/" + "token-images/";

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
  const currentness = digestCurrentnessView(digest, dataGaps[0] ?? null);

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
      logoUrl: localLogoUrl(profileIdentity?.logo_url),
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
      currentness,
      statusPills: digestStatusPills(digest, currentness),
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
    cexDetail: buildCexDetailView(dossier.cex_detail),
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

function localLogoUrl(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed?.startsWith(LOCAL_LOGO_PREFIX) ? trimmed : null;
}

function buildCexDetailView(snapshot?: CexDetailSnapshot | null): TokenCaseViewModel["cexDetail"] {
  if (!snapshot || snapshot.status === "missing") {
    return null;
  }
  const exchange = titleCase(stringValue(snapshot.exchange) ?? "binance");
  const nativeMarketId = stringValue(snapshot.native_market_id) ?? "-";
  const status = stringValue(snapshot.status) ?? "partial";
  const computedAt = numberValue(snapshot.computed_at_ms);
  const observedAt = numberValue(snapshot.observed_at_ms);
  const metrics: TokenCaseMetric[] = [
    metric(
      "mark_price",
      "mark",
      formatTokenPriceUsd(numberValue(snapshot.mark_price)),
      "binance",
      "info",
    ),
    metric(
      "open_interest",
      "open interest",
      formatUsdCompact(numberValue(snapshot.open_interest_usd)),
      "notional",
      "health",
    ),
    metric(
      "volume_24h",
      "volume 24h",
      formatUsdCompact(numberValue(snapshot.volume_24h_usd)),
      "turnover",
      "neutral",
    ),
    metric(
      "funding",
      "funding",
      formatSignedRatioPercent(numberValue(snapshot.funding_rate)),
      "current",
      fundingTone(numberValue(snapshot.funding_rate)),
    ),
    metric(
      "long_short",
      "long/short",
      formatRatio(numberValue(snapshot.long_short_ratio)),
      "account ratio",
      "neutral",
    ),
    metric(
      "top_trader",
      "top trader",
      formatRatio(numberValue(snapshot.top_trader_position_ratio)),
      "position ratio",
      "neutral",
    ),
  ].filter((item) => item.value !== "-");
  const oiDeltas = [
    delta("OI 1h", numberValue(snapshot.oi_change_pct_1h), "percent_point"),
    delta("OI 4h", numberValue(snapshot.oi_change_pct_4h), "percent_point"),
    delta("OI 24h", numberValue(snapshot.oi_change_pct_24h), "percent_point"),
  ].filter((item) => item.value !== "-");
  const cvdDeltas = [
    delta("CVD 1h", numberValue(snapshot.cvd_delta_1h), "usd"),
    delta("CVD 4h", numberValue(snapshot.cvd_delta_4h), "usd"),
    delta("CVD 24h", numberValue(snapshot.cvd_delta_24h), "usd"),
  ].filter((item) => item.value !== "-");
  return {
    statusLabel: status,
    tone: status === "ready" ? "health" : "warn",
    instrumentLabel: `${exchange} · ${nativeMarketId}`,
    freshnessLabel:
      computedAt || observedAt
        ? `snapshot ${timeAgoLabel(computedAt ?? observedAt ?? Date.now())}`
        : null,
    metrics,
    oiDeltas,
    cvdDeltas,
    levels: (snapshot.level_bands ?? []).slice(0, 5).map((level) => ({
      kind: stringValue(level.kind) ?? "level",
      priceLabel: formatTokenPriceUsd(numberValue(level.price)),
      scoreLabel:
        numberValue(level.score) === null
          ? null
          : `${Math.round(numberValue(level.score)! * 100)} score`,
      tone: levelTone(stringValue(level.kind)),
    })),
    dataGaps: (snapshot.degraded_reasons ?? []).map(cexGapLabel),
  };
}

function metric(
  key: string,
  label: string,
  value: string,
  detail: string,
  tone: TokenCaseTone,
): TokenCaseMetric {
  return { key, label, value, detail, tone };
}

function delta(
  label: string,
  value: number | null,
  mode: "percent_point" | "usd",
): { label: string; value: string; tone: TokenCaseTone } {
  return {
    label,
    value: mode === "usd" ? formatSignedUsdCompact(value) : formatSignedPercentPoint(value),
    tone: signedTone(value),
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
  const openInterest = numberValue(live.open_interest_usd);
  const ready = status === "ready" || status === "live";
  return {
    status,
    provider: stringValue(live.provider),
    priceLabel: price === null ? "-" : formatTokenPriceUsd(price),
    marketCapLabel: marketCap === null ? "-" : formatUsdCompact(marketCap),
    liquidityLabel: liquidity === null ? "-" : formatUsdCompact(liquidity),
    holdersLabel: holders === null ? "-" : compactNumber(holders),
    volume24hLabel: volume24h === null ? "-" : formatUsdCompact(volume24h),
    openInterestLabel: openInterest === null ? "-" : formatUsdCompact(openInterest),
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
  currentness: TokenCaseViewModel["propagation"]["currentness"],
): Array<{ label: string; tone: TokenCaseTone }> {
  const pills: Array<{ label: string; tone: TokenCaseTone }> = [
    { label: digestStatusLabel(digest.status), tone: digestStatusTone(digest.status) },
    { label: currentness.label, tone: currentness.tone },
  ];
  if (currentness.deltaLabel) {
    pills.push({ label: currentness.deltaLabel, tone: "info" });
  }
  if (currentness.lastReadyComputedLabel) {
    pills.push({ label: `last ready ${currentness.lastReadyComputedLabel}`, tone: "neutral" });
  }
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

function digestCurrentnessView(
  digest: TokenDiscussionDigest,
  firstDataGapLabel: string | null,
): TokenCaseViewModel["propagation"]["currentness"] {
  const currentness = digest.currentness;
  const displayStatus = currentness.display_status;
  const deltaSourceEventCount = nonNegativeNumber(currentness.delta_source_event_count);
  const deltaIndependentAuthorCount = nonNegativeNumber(currentness.delta_independent_author_count);
  const lastReadyComputedAtMs = numberValue(currentness.last_ready_computed_at_ms);
  const deltaLabel = currentnessDeltaLabel(deltaSourceEventCount, deltaIndependentAuthorCount);
  return {
    displayStatus,
    reason: cleanText(currentness.reason),
    label: currentnessLabel(displayStatus, deltaSourceEventCount, firstDataGapLabel),
    tone: currentnessTone(displayStatus),
    lastReadyComputedAtMs,
    lastReadyComputedLabel: lastReadyComputedAtMs ? timeAgoLabel(lastReadyComputedAtMs) : null,
    deltaSourceEventCount,
    deltaIndependentAuthorCount,
    deltaLabel,
  };
}

function currentnessLabel(
  displayStatus: string,
  deltaSourceEventCount: number,
  firstDataGapLabel: string | null,
): string {
  if (displayStatus === "updating") {
    return `叙事更新中 +${compactNumber(deltaSourceEventCount)}`;
  }
  const labels: Record<string, string> = {
    current: "叙事已更新",
    not_ready: firstDataGapLabel ?? "叙事待生成",
    out_of_frontier: "不在当前雷达前沿",
    stale: "上一版",
    unsupported_window: "5m 实时信号",
  };
  return labels[displayStatus] ?? displayStatus.replaceAll("_", " ");
}

function currentnessTone(displayStatus: string): TokenCaseTone {
  if (displayStatus === "current") {
    return "health";
  }
  if (displayStatus === "updating" || displayStatus === "unsupported_window") {
    return "info";
  }
  if (displayStatus === "stale" || displayStatus === "out_of_frontier") {
    return "warn";
  }
  return "neutral";
}

function currentnessDeltaLabel(sourceCount: number, authorCount: number): string | null {
  const parts = [
    sourceCount > 0 ? `+${compactNumber(sourceCount)} posts` : null,
    authorCount > 0 ? `+${compactNumber(authorCount)} authors` : null,
  ].filter((part): part is string => Boolean(part));
  return parts.length ? parts.join(" · ") : null;
}

function nonNegativeNumber(value: unknown): number {
  const parsed = numberValue(value);
  return parsed === null ? 0 : Math.max(0, parsed);
}

function digestStages(
  clusters: NarrativeCluster[],
  digest: TokenDiscussionDigest,
): TokenCaseViewModel["propagation"]["stages"] {
  const fromClusters = clusters.slice(0, 3).map((cluster) => {
    const state =
      cluster.propagation_state ?? digestPropagationState(digest) ?? cluster.cluster_key;
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

function formatSignedPercentPoint(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }
  const abs = Math.abs(value);
  const formatted = abs >= 10 ? String(Math.round(abs)) : trimOneDecimal(abs);
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${formatted}%`;
}

function formatSignedRatioPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }
  return formatSignedPercentPoint(value * 100);
}

function formatSignedUsdCompact(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatUsdCompact(Math.abs(value))}`;
}

function formatRatio(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }
  return `${trimOneDecimal(value)}x`;
}

function signedTone(value: number | null): TokenCaseTone {
  if (value === null || Math.abs(value) < 0.000001) {
    return "neutral";
  }
  return value > 0 ? "health" : "risk";
}

function fundingTone(value: number | null): TokenCaseTone {
  if (value === null || Math.abs(value) < 0.000001) {
    return "neutral";
  }
  return value > 0 ? "opportunity" : "info";
}

function levelTone(kind: string | null): TokenCaseTone {
  const normalized = kind?.toLowerCase();
  if (normalized === "support") {
    return "health";
  }
  if (normalized === "resistance") {
    return "risk";
  }
  return "info";
}

function cexGapLabel(reason: string): string {
  const labels: Record<string, string> = {
    cex_detail_snapshot_missing: "CEX detail snapshot missing",
    coinglass_unavailable: "CoinGlass unavailable",
    oi_change_period_5m_not_1h: "OI delta is not hourly yet",
  };
  return labels[reason] ?? reason.replaceAll("_", " ");
}

function titleCase(value: string): string {
  return value ? `${value.slice(0, 1).toUpperCase()}${value.slice(1).toLowerCase()}` : value;
}

function trimOneDecimal(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
