import { compactNumber, formatTokenPriceUsd, formatUsdCompact, shortAddress } from "@lib/format";
import type {
  CexDetailSnapshot,
  NarrativeAdmission,
  TokenCaseDossier,
  TokenCasePostsData,
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
  const admission = dossier.narrative_admission;
  const dataGaps = narrativeGapLabels(admission.data_gaps);

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
        key: "admission",
        label: "admission",
        value: admissionStatusLabel(admission),
        detail: admissionCoverageLabel(admission),
        tone: admissionTone(admission),
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
    dataGaps,
  };
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
  const pricePill = tokenPricePill(post.price?.price_usd, post.price?.status);
  return pricePill ? [pricePill] : [];
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

function admissionStatusLabel(admission: NarrativeAdmission): string {
  const labels: Record<string, string> = {
    admitted: "admitted",
    missing: "not admitted",
    suppressed: "suppressed",
    unsupported_window: "unsupported",
  };
  return labels[admission.status] ?? admission.status.replaceAll("_", " ");
}

function admissionCoverageLabel(admission: NarrativeAdmission): string {
  return `${compactNumber(admission.coverage.source_mentions)} posts · ${compactNumber(
    admission.coverage.independent_authors,
  )} authors`;
}

function admissionTone(admission: NarrativeAdmission): TokenCaseTone {
  if (admission.status === "admitted" && admission.currentness.display_status === "current") {
    return "health";
  }
  if (
    admission.status === "suppressed" ||
    admission.currentness.display_status === "out_of_frontier"
  ) {
    return "warn";
  }
  return "info";
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
