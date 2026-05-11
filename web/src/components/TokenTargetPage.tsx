import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { getApi } from "../api/client";
import type {
  AssetFlowData,
  TokenFlowItem,
  TokenPostRange,
  TokenPostSortMode,
  TokenSocialTimelineData,
  TokenTimelinePost,
  TokenTimelineStage,
  WindowKey,
} from "../api/types";
import {
  mergeTokenPostPages,
  useTokenTargetPosts,
  useTokenTargetTimeline,
} from "../api/useTokenTargetQueries";
import { type TargetRef, targetRefEquals } from "../domain/tokenTarget";
import {
  compactNumber,
  eventText,
  formatReason,
  formatRisk,
  formatScore,
  formatSignedPercent,
  formatTokenPriceUsd,
  formatUsdCompact,
  shortAddress,
  tokenLabel,
} from "../lib/format";
import { OBSERVATION_WINDOWS } from "../lib/observationWindows";
import { tokenRadarRowToTokenItem } from "../lib/tokenRadar";
import { tokenVenueAction } from "../lib/venue";
import { useTraderStore } from "../store/useTraderStore";

import { DecisionTag } from "./DecisionTag";
import { ScoreLedger } from "./ScoreLedger";
import { TokenPostsPanel } from "./TokenPostsPanel";

const VALID_TARGET_TYPES = new Set<TargetRef["target_type"]>(["Asset", "CexToken"]);

export function TokenTargetPage() {
  const navigate = useNavigate();
  const params = useParams<{ targetType: string; targetId: string }>();
  const [searchParams] = useSearchParams();
  const token = useTraderStore((state) => state.token);
  const storeScope = useTraderStore((state) => state.scope);
  const scope = parseScopeKey(searchParams.get("scope")) ?? storeScope;

  const [windowKey, setWindowKey] = useState<WindowKey>(
    () => parseWindowKey(searchParams.get("window")) ?? "1h",
  );
  const [postRange, setPostRange] = useState<TokenPostRange>("current_window");
  const [postSortMode, setPostSortMode] = useState<TokenPostSortMode>("recent");
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [watchedPostsOnly, setWatchedPostsOnly] = useState(false);
  const [hideDuplicateClusters, setHideDuplicateClusters] = useState(false);

  const targetType = params.targetType as TargetRef["target_type"] | undefined;
  const isValidTargetType = Boolean(targetType && VALID_TARGET_TYPES.has(targetType));
  const isValidParams = isValidTargetType && Boolean(params.targetId);
  const target = useMemo<TargetRef | null>(
    () =>
      isValidParams && targetType && params.targetId
        ? { target_type: targetType, target_id: params.targetId }
        : null,
    [isValidParams, params.targetId, targetType],
  );

  const tokenPostRequestSort = postSortMode === "catalyst" ? "catalyst" : "recent";

  const assetFlowQuery = useQuery({
    queryKey: [
      "token-radar-page",
      windowKey,
      scope,
      target?.target_type ?? null,
      target?.target_id ?? null,
    ],
    queryFn: () =>
      getApi<AssetFlowData>("/api/token-radar", {
        token,
        params: { window: windowKey, limit: 48, scope },
      }),
    enabled: Boolean(token && target),
    refetchInterval: 10_000,
  });

  const timelineQuery = useTokenTargetTimeline({ token, target, window: windowKey, scope });
  const postsQuery = useTokenTargetPosts({
    token,
    target,
    window: windowKey,
    scope,
    range: postRange,
    sort: tokenPostRequestSort,
  });

  const tokenItem = useMemo(() => {
    if (!target) return null;
    const data = assetFlowQuery.data?.data;
    if (!data) return null;
    const rows = [...data.targets, ...data.attention];
    const matchedRow = rows.find((row) => {
      const rowTarget: TargetRef | null =
        row.target?.target_type && row.target.target_id
          ? {
              target_type: row.target.target_type as TargetRef["target_type"],
              target_id: row.target.target_id,
            }
          : null;
      return rowTarget && targetRefEquals(rowTarget, target);
    });
    if (!matchedRow) return null;
    return tokenRadarRowToTokenItem(matchedRow, windowKey, scope);
  }, [assetFlowQuery.data?.data, scope, target, windowKey]);

  const timeline = timelineQuery.data?.data ?? null;
  const posts = mergeTokenPostPages(postsQuery.data?.pages);

  if (!isValidParams) {
    return (
      <section className="mobile-task-surface" data-mobile-task-panel="radar">
        <section className="token-target-page" aria-label="Token audit page (not found)">
          <header className="token-case-header">
            <button
              className="ghost-icon-button"
              type="button"
              onClick={() => navigate("/")}
              aria-label="Back to Live"
            >
              <ArrowLeft aria-hidden />
              <span>Live</span>
            </button>
          </header>
          <div className="empty-state">Token 不存在或链接已失效</div>
        </section>
      </section>
    );
  }

  if (!tokenItem) {
    if (!assetFlowQuery.isPending && target) {
      const stages = timeline?.stages ?? [];
      const selectedStageFilter =
        selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId)
          ? selectedStageId
          : null;
      return (
        <section className="mobile-task-surface" data-mobile-task-panel="radar">
          <section className="token-target-page" aria-label="Token audit page">
            <header className="token-case-header">
              <button
                className="ghost-icon-button"
                type="button"
                onClick={() => navigate(-1)}
                aria-label="Back to Token Radar"
              >
                <ArrowLeft aria-hidden />
                <span>Radar</span>
              </button>
              <div className="token-case-title">
                <span>
                  {target.target_type} · {target.target_id}
                </span>
                <h2>{targetDisplayLabel(target)}</h2>
              </div>
              <div className="token-case-actions">
                <div className="segmented mini range" aria-label="audit page window">
                  {OBSERVATION_WINDOWS.map((item) => (
                    <button
                      key={item}
                      className={windowKey === item ? "active" : ""}
                      type="button"
                      onClick={() => setWindowKey(item)}
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            </header>

            <div className="route-state-panel">
              <b>Not in current radar window</b>
              <p>
                This route target has no Token Radar row for {windowKey}. Timeline and posts can
                still load, but no score audit is shown without a real radar row.
              </p>
            </div>

            <section className="case-section stage-tape-section">
              <header>
                <span>stage tape</span>
                <b>
                  {timelineQuery.isFetching
                    ? "loading"
                    : `${stages.length} stages · ${compactNumber(timeline?.summary.posts ?? 0)} posts`}
                </b>
                {selectedStageFilter ? (
                  <button
                    className="inline-clear-button"
                    type="button"
                    onClick={() => setSelectedStageId(null)}
                  >
                    clear filter
                  </button>
                ) : null}
              </header>
              <StageTape
                stages={stages}
                selectedStageId={selectedStageFilter}
                timeline={timeline}
                onSelect={setSelectedStageId}
              />
            </section>

            <section className="case-section">
              <header>
                <span>message evidence</span>
                <b>{selectedStageFilter ? "stage filtered" : "all loaded posts"}</b>
              </header>
              <TokenPostsPanel
                hideDuplicateClusters={hideDuplicateClusters}
                isFetchingNextPage={postsQuery.isFetchingNextPage}
                isLoading={postsQuery.isLoading}
                posts={posts}
                postRange={postRange}
                postSortMode={postSortMode}
                selectedStageId={selectedStageFilter}
                watchedPostsOnly={watchedPostsOnly}
                onHideDuplicateClustersChange={setHideDuplicateClusters}
                onLoadMorePosts={() => void postsQuery.fetchNextPage()}
                onPostRangeChange={setPostRange}
                onPostSortModeChange={setPostSortMode}
                onWatchedPostsOnlyChange={setWatchedPostsOnly}
              />
            </section>
          </section>
        </section>
      );
    }
    return (
      <section className="mobile-task-surface" data-mobile-task-panel="radar">
        <section className="token-target-page" aria-label="Token audit page">
          <header className="token-case-header">
            <button
              className="ghost-icon-button"
              type="button"
              onClick={() => navigate(-1)}
              aria-label="Back"
            >
              <ArrowLeft aria-hidden />
              <span>Back</span>
            </button>
          </header>
          <div className="empty-state">
            {assetFlowQuery.isPending ? "loading token audit" : "token audit target missing"}
          </div>
        </section>
      </section>
    );
  }

  const stages = timeline?.stages ?? [];
  const selectedStageFilter =
    selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId)
      ? selectedStageId
      : null;
  const venueAction = tokenVenueAction(tokenItem);
  const riskLead =
    tokenItem.opportunity.hard_risks?.[0] ??
    tokenItem.opportunity.risks[0] ??
    tokenItem.timing.risks[0];

  return (
    <section className="mobile-task-surface" data-mobile-task-panel="radar">
      <section className="token-target-page" aria-label="Token audit page">
        <header className="token-case-header">
          <button
            className="ghost-icon-button"
            type="button"
            onClick={() => navigate(-1)}
            aria-label="Back to Token Radar"
          >
            <ArrowLeft aria-hidden />
            <span>Radar</span>
          </button>
          <div className="token-case-title">
            <span>
              {tokenItem.identity.target_type ?? "unresolved"} ·{" "}
              {tokenItem.identity.inst_id ??
                tokenItem.identity.chain ??
                tokenItem.identity.identity_key}
            </span>
            <h2>{tokenLabel(tokenItem)}</h2>
          </div>
          <div className="token-case-actions">
            <DecisionTag decision={tokenItem.opportunity.decision} />
            <strong>{formatScore(tokenItem.opportunity.score)}</strong>
            <div className="segmented mini range" aria-label="audit page window">
              {OBSERVATION_WINDOWS.map((item) => (
                <button
                  key={item}
                  className={windowKey === item ? "active" : ""}
                  type="button"
                  onClick={() => setWindowKey(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            {venueAction ? (
              <a
                aria-label={`Open ${tokenLabel(tokenItem)} on ${venueAction.label}`}
                href={venueAction.url}
                rel="noreferrer"
                target="_blank"
              >
                {venueAction.label}
                <ExternalLink aria-hidden />
              </a>
            ) : null}
          </div>
        </header>

        <section className="token-audit-strip" aria-label="token audit facts">
          <AuditMetric
            label="identity"
            value={identityLine(tokenItem)}
            detail={tokenItem.identity.identity_status}
          />
          <AuditMetric
            label="social"
            value={`${compactNumber(timeline?.summary.posts ?? tokenItem.evidence_total_count)} posts`}
            detail={`${compactNumber(timeline?.summary.authors ?? tokenItem.propagation.independent_authors)} authors`}
          />
          <AuditMetric
            label="market"
            value={marketLine(tokenItem)}
            detail={tokenItem.market.price_change_status ?? tokenItem.market.market_status}
          />
          <AuditMetric
            label="since social"
            value={formatSignedPercent(tokenItem.market.price_change_since_social_pct)}
            detail={
              tokenItem.market.price_at_social_start
                ? formatTokenPriceUsd(tokenItem.market.price_at_social_start)
                : "no start price"
            }
          />
          <AuditMetric
            label="first snapshot"
            value={formatSignedPercent(tokenItem.market.price_change_since_first_snapshot_pct)}
            detail={
              tokenItem.market.price_at_first_snapshot
                ? formatTokenPriceUsd(tokenItem.market.price_at_first_snapshot)
                : "no snapshot"
            }
          />
          <AuditMetric
            label="risk"
            value={riskLead ? formatRisk(riskLead) : "clear"}
            detail={tokenItem.flow.baseline_status}
          />
        </section>

        <section className="case-section stage-tape-section">
          <header>
            <span>stage tape</span>
            <b>
              {timelineQuery.isFetching
                ? "loading"
                : `${stages.length} stages · ${compactNumber(timeline?.summary.posts ?? 0)} posts`}
            </b>
            {selectedStageFilter ? (
              <button
                className="inline-clear-button"
                type="button"
                onClick={() => setSelectedStageId(null)}
              >
                clear filter
              </button>
            ) : null}
          </header>
          <StageTape
            stages={stages}
            selectedStageId={selectedStageFilter}
            timeline={timeline}
            onSelect={setSelectedStageId}
          />
        </section>

        <section className="case-section">
          <header>
            <span>message evidence</span>
            <b>{selectedStageFilter ? "stage filtered" : "all loaded posts"}</b>
          </header>
          <TokenPostsPanel
            hideDuplicateClusters={hideDuplicateClusters}
            isFetchingNextPage={postsQuery.isFetchingNextPage}
            isLoading={postsQuery.isLoading}
            posts={posts}
            postRange={postRange}
            postSortMode={postSortMode}
            selectedStageId={selectedStageFilter}
            watchedPostsOnly={watchedPostsOnly}
            onHideDuplicateClustersChange={setHideDuplicateClusters}
            onLoadMorePosts={() => void postsQuery.fetchNextPage()}
            onPostRangeChange={setPostRange}
            onPostSortModeChange={setPostSortMode}
            onWatchedPostsOnlyChange={setWatchedPostsOnly}
          />
        </section>

        <section className="case-section">
          <header>
            <span>score audit</span>
            <b>{tokenItem.opportunity.score_version}</b>
          </header>
          <ScoreLedger token={tokenItem} />
        </section>
      </section>
    </section>
  );
}

function AuditMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string | null;
}) {
  return (
    <div>
      <span>{label}</span>
      <b>{value || "-"}</b>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function StageTape({
  stages,
  selectedStageId,
  timeline,
  onSelect,
}: {
  stages: TokenTimelineStage[];
  selectedStageId: string | null;
  timeline: TokenSocialTimelineData | null;
  onSelect: (stageId: string | null) => void;
}) {
  if (!stages.length) {
    return <div className="empty-state">暂无阶段证据</div>;
  }
  return (
    <div className="stage-tape">
      {stages.map((stage) => {
        const posts = representativePosts(stage, timeline);
        const lead = posts[0];
        return (
          <button
            key={stage.stage_id}
            className={selectedStageId === stage.stage_id ? "active" : ""}
            type="button"
            onClick={() => onSelect(stage.stage_id)}
            aria-label={`select stage ${stage.phase}`}
          >
            <span className="stage-phase">{stage.phase}</span>
            <span>
              {compactNumber(stage.people.posts)}p · {compactNumber(stage.people.authors)}a · top{" "}
              {Math.round(stage.people.top_author_share * 100)}%
            </span>
            <span className={(stage.price.delta_pct ?? 0) >= 0 ? "up" : "down"}>
              {stage.price.status} {formatSignedPercent(stage.price.delta_pct)}
            </span>
            <span>{formatReason(stage.trigger_reason)}</span>
            <p>
              {lead
                ? `@${lead.handle ?? "unknown"} · ${eventText({ event_id: lead.event_id, text_clean: lead.text })}`
                : "no representative post"}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function representativePosts(
  stage: TokenTimelineStage,
  timeline: TokenSocialTimelineData | null,
): TokenTimelinePost[] {
  const stagePosts = timeline?.posts ?? [];
  const representativeIds = new Set(stage.representative_event_ids);
  return stagePosts
    .filter((post) => post.stage_id === stage.stage_id || representativeIds.has(post.event_id))
    .slice(0, 3);
}

function parseWindowKey(value: string | null): WindowKey | null {
  return OBSERVATION_WINDOWS.includes(value as WindowKey) ? (value as WindowKey) : null;
}

function parseScopeKey(value: string | null): TokenFlowItem["posts_query"]["scope"] | null {
  return value === "all" || value === "matched" ? value : null;
}

function symbolFromTarget(target: TargetRef): string | null {
  if (target.target_type !== "CexToken") {
    return null;
  }
  const raw = target.target_id.startsWith("cex_token:")
    ? target.target_id.slice("cex_token:".length)
    : target.target_id;
  const symbol = raw
    .split(":")
    .pop()
    ?.replace(/-USDT$/i, "")
    .trim()
    .toUpperCase();
  return symbol || null;
}

function targetDisplayLabel(target: TargetRef): string {
  if (target.target_type === "CexToken") {
    const symbol = symbolFromTarget(target);
    return symbol ? `$${symbol}` : target.target_id;
  }
  const address = target.target_id.split(":").at(-1);
  return address ? shortAddress(address) : target.target_id;
}

function identityLine(token: TokenFlowItem): string {
  if (token.identity.venue_type === "cex") {
    return (
      [token.identity.exchange?.toUpperCase(), token.identity.inst_id]
        .filter(Boolean)
        .join(" · ") || "CEX"
    );
  }
  if (token.identity.address) {
    return `${token.identity.chain ?? "chain?"} · ${shortAddress(token.identity.address)}`;
  }
  return token.identity.target_type ?? "unresolved";
}

function marketLine(token: TokenFlowItem): string {
  if (token.market.market_cap !== null && token.market.market_cap !== undefined) {
    return formatUsdCompact(token.market.market_cap);
  }
  if (token.market.price !== null && token.market.price !== undefined) {
    return formatTokenPriceUsd(token.market.price);
  }
  return token.market.market_status ?? "-";
}
