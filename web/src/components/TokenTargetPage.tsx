import { useState } from "react";
import { ArrowLeft, ExternalLink } from "lucide-react";
import type { TokenFlowItem, TokenPostRange, TokenPostSortMode, TokenPostsData, TokenSocialTimelineData, TokenTimelinePost, TokenTimelineStage, WindowKey } from "../api/types";
import { compactNumber, eventText, formatReason, formatRisk, formatScore, formatSignedPercent, formatTokenPriceUsd, formatUsdCompact, shortAddress, tokenLabel } from "../lib/format";
import { OBSERVATION_WINDOWS } from "../lib/observationWindows";
import { tokenVenueAction } from "../lib/venue";
import { DecisionTag } from "./DecisionTag";
import { ScoreLedger } from "./ScoreLedger";
import { TokenPostsPanel } from "./TokenPostsPanel";

type TokenTargetPageProps = {
  token: TokenFlowItem;
  timeline: TokenSocialTimelineData | null;
  posts: TokenPostsData | null;
  windowKey: WindowKey;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  selectedStageId: string | null;
  isTimelineLoading: boolean;
  isPostsLoading: boolean;
  isPostsFetchingNextPage: boolean;
  onBack: () => void;
  onWindowChange: (window: WindowKey) => void;
  onPostRangeChange: (range: TokenPostRange) => void;
  onPostSortModeChange: (mode: TokenPostSortMode) => void;
  onStageSelect: (stageId: string | null) => void;
  onLoadMorePosts: () => void;
};

export function TokenTargetPage({
  token,
  timeline,
  posts,
  windowKey,
  postRange,
  postSortMode,
  selectedStageId,
  isTimelineLoading,
  isPostsLoading,
  isPostsFetchingNextPage,
  onBack,
  onWindowChange,
  onPostRangeChange,
  onPostSortModeChange,
  onStageSelect,
  onLoadMorePosts
}: TokenTargetPageProps) {
  const [watchedPostsOnly, setWatchedPostsOnly] = useState(false);
  const [hideDuplicateClusters, setHideDuplicateClusters] = useState(false);
  const stages = timeline?.stages ?? [];
  const selectedStageFilter = selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId) ? selectedStageId : null;
  const venueAction = tokenVenueAction(token);
  const riskLead = token.opportunity.hard_risks?.[0] ?? token.opportunity.risks[0] ?? token.timing.risks[0];

  return (
    <section className="token-target-page" aria-label="Token audit page">
      <header className="token-case-header">
        <button className="ghost-icon-button" type="button" onClick={onBack} aria-label="Back to Token Radar">
          <ArrowLeft aria-hidden />
          <span>Radar</span>
        </button>
        <div className="token-case-title">
          <span>{token.identity.target_type ?? "unresolved"} · {token.identity.inst_id ?? token.identity.chain ?? token.identity.identity_key}</span>
          <h2>{tokenLabel(token)}</h2>
        </div>
        <div className="token-case-actions">
          <DecisionTag decision={token.opportunity.decision} />
          <strong>{formatScore(token.opportunity.score)}</strong>
          <div className="segmented mini range" aria-label="audit page window">
            {OBSERVATION_WINDOWS.map((item) => (
              <button key={item} className={windowKey === item ? "active" : ""} type="button" onClick={() => onWindowChange(item)}>
                {item}
              </button>
            ))}
          </div>
          {venueAction ? (
            <a aria-label={`Open ${tokenLabel(token)} on ${venueAction.label}`} href={venueAction.url} rel="noreferrer" target="_blank">
              {venueAction.label}
              <ExternalLink aria-hidden />
            </a>
          ) : null}
        </div>
      </header>

      <section className="token-audit-strip" aria-label="token audit facts">
        <AuditMetric label="identity" value={identityLine(token)} detail={token.identity.identity_status} />
        <AuditMetric label="social" value={`${compactNumber(timeline?.summary.posts ?? token.evidence_total_count)} posts`} detail={`${compactNumber(timeline?.summary.authors ?? token.propagation.independent_authors)} authors`} />
        <AuditMetric label="market" value={marketLine(token)} detail={token.market.price_change_status ?? token.market.market_status} />
        <AuditMetric label="since social" value={formatSignedPercent(token.market.price_change_since_social_pct)} detail={token.market.price_at_social_start ? formatTokenPriceUsd(token.market.price_at_social_start) : "no start price"} />
        <AuditMetric label="first snapshot" value={formatSignedPercent(token.market.price_change_since_first_snapshot_pct)} detail={token.market.price_at_first_snapshot ? formatTokenPriceUsd(token.market.price_at_first_snapshot) : "no snapshot"} />
        <AuditMetric label="risk" value={riskLead ? formatRisk(riskLead) : "clear"} detail={token.flow.baseline_status} />
      </section>

      <section className="case-section stage-tape-section">
        <header>
          <span>stage tape</span>
          <b>{isTimelineLoading ? "loading" : `${stages.length} stages · ${compactNumber(timeline?.summary.posts ?? 0)} posts`}</b>
          {selectedStageFilter ? (
            <button className="inline-clear-button" type="button" onClick={() => onStageSelect(null)}>
              clear filter
            </button>
          ) : null}
        </header>
        <StageTape stages={stages} selectedStageId={selectedStageFilter} timeline={timeline} onSelect={onStageSelect} />
      </section>

      <section className="case-section">
        <header>
          <span>message evidence</span>
          <b>{selectedStageFilter ? "stage filtered" : "all loaded posts"}</b>
        </header>
        <TokenPostsPanel
          hideDuplicateClusters={hideDuplicateClusters}
          isFetchingNextPage={isPostsFetchingNextPage}
          isLoading={isPostsLoading}
          posts={posts}
          postRange={postRange}
          postSortMode={postSortMode}
          selectedStageId={selectedStageFilter}
          watchedPostsOnly={watchedPostsOnly}
          onHideDuplicateClustersChange={setHideDuplicateClusters}
          onLoadMorePosts={onLoadMorePosts}
          onPostRangeChange={onPostRangeChange}
          onPostSortModeChange={onPostSortModeChange}
          onWatchedPostsOnlyChange={setWatchedPostsOnly}
        />
      </section>

      <section className="case-section">
        <header>
          <span>score audit</span>
          <b>{token.opportunity.score_version}</b>
        </header>
        <ScoreLedger token={token} />
      </section>
    </section>
  );
}

function AuditMetric({ label, value, detail }: { label: string; value: string; detail?: string | null }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value || "-"}</b>
      {detail ? <em>{detail}</em> : null}
    </div>
  );
}

function StageTape({ stages, selectedStageId, timeline, onSelect }: { stages: TokenTimelineStage[]; selectedStageId: string | null; timeline: TokenSocialTimelineData | null; onSelect: (stageId: string | null) => void }) {
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
            <span>{compactNumber(stage.people.posts)}p · {compactNumber(stage.people.authors)}a · top {Math.round(stage.people.top_author_share * 100)}%</span>
            <span className={(stage.price.delta_pct ?? 0) >= 0 ? "up" : "down"}>{stage.price.status} {formatSignedPercent(stage.price.delta_pct)}</span>
            <span>{formatReason(stage.trigger_reason)}</span>
            <p>{lead ? `@${lead.handle ?? "unknown"} · ${eventText({ event_id: lead.event_id, text_clean: lead.text })}` : "no representative post"}</p>
          </button>
        );
      })}
    </div>
  );
}

function representativePosts(stage: TokenTimelineStage, timeline: TokenSocialTimelineData | null): TokenTimelinePost[] {
  const stagePosts = timeline?.posts ?? [];
  const representativeIds = new Set(stage.representative_event_ids);
  return stagePosts.filter((post) => post.stage_id === stage.stage_id || representativeIds.has(post.event_id)).slice(0, 3);
}

function identityLine(token: TokenFlowItem): string {
  if (token.identity.venue_type === "cex") {
    return [token.identity.exchange?.toUpperCase(), token.identity.inst_id].filter(Boolean).join(" · ") || "CEX";
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
