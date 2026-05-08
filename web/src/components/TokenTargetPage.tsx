import { useMemo, useState } from "react";
import { ArrowLeft, ExternalLink } from "lucide-react";
import type { TokenFlowItem, TokenPostRange, TokenPostSortMode, TokenPostsData, TokenSocialTimelineData, TokenTimelineStage, WindowKey } from "../api/types";
import { compactNumber, eventText, formatReason, formatRelativeTime, formatRisk, formatScore, formatSignedPercent, formatTokenPriceUsd, tokenLabel } from "../lib/format";
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
  const inspectedStage = useMemo(
    () => stages.find((stage) => stage.stage_id === selectedStageId) ?? stages[stages.length - 1] ?? null,
    [selectedStageId, stages]
  );
  const selectedStageFilter = selectedStageId && stages.some((stage) => stage.stage_id === selectedStageId) ? selectedStageId : null;
  const venueAction = tokenVenueAction(token);

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
          {venueAction ? (
            <a aria-label={`Open ${tokenLabel(token)} on ${venueAction.label}`} href={venueAction.url} rel="noreferrer" target="_blank">
              {venueAction.label}
              <ExternalLink aria-hidden />
            </a>
          ) : null}
        </div>
      </header>

      <section className="token-thesis-strip" aria-label="token trading thesis">
        <div>
          <span>current phase</span>
          <b>{inspectedStage?.phase ?? token.propagation.phase}</b>
        </div>
        <div>
          <span>social vs price</span>
          <b>{priceRelation(token)}</b>
        </div>
        <div>
          <span>people</span>
          <b>{compactNumber(timeline?.summary.authors ?? token.propagation.independent_authors)} authors · {compactNumber(timeline?.summary.posts ?? token.evidence_total_count)} posts</b>
        </div>
        <div>
          <span>risk</span>
          <b>{formatRisk(token.opportunity.hard_risks?.[0] ?? token.opportunity.risks[0] ?? token.timing.risks[0])}</b>
        </div>
      </section>

      <section className="token-case-controls">
        <div className="segmented mini range" aria-label="audit page window">
          {OBSERVATION_WINDOWS.map((item) => (
            <button key={item} className={windowKey === item ? "active" : ""} type="button" onClick={() => onWindowChange(item)}>
              {item}
            </button>
          ))}
        </div>
        {selectedStageFilter ? (
          <button className="venue-link" type="button" onClick={() => onStageSelect(null)}>
            clear stage filter
          </button>
        ) : null}
      </section>

      <MarketLedger token={token} />

      <section className="token-case-grid">
        <section className="case-section stage-timeline-section">
          <header>
            <span>stage timeline</span>
            <b>{isTimelineLoading ? "loading" : `${stages.length} stages`}</b>
          </header>
          <StageTimeline stages={stages} selectedStageId={inspectedStage?.stage_id ?? null} onSelect={onStageSelect} />
        </section>

        <section className="case-section stage-inspector-section">
          <header>
            <span>stage evidence</span>
            <b>{inspectedStage?.phase ?? "-"}</b>
          </header>
          <StageInspector stage={inspectedStage} timeline={timeline} />
        </section>
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

function MarketLedger({ token }: { token: TokenFlowItem }) {
  return (
    <section className="market-ledger-band" aria-label="market ledger">
      <LedgerMetric label="first snapshot" value={token.market.price_at_first_snapshot} delta={token.market.price_change_since_first_snapshot_pct} />
      <LedgerMetric label="social start" value={token.market.price_at_social_start} delta={token.market.price_change_since_social_pct} />
      <LedgerMetric label="latest" value={token.market.price_at_reference ?? token.market.price} delta={null} />
      <LedgerMetric label="volume" value={token.market.volume_24h} delta={null} compact />
    </section>
  );
}

function StageTimeline({ stages, selectedStageId, onSelect }: { stages: TokenTimelineStage[]; selectedStageId: string | null; onSelect: (stageId: string | null) => void }) {
  if (!stages.length) {
    return <div className="empty-state">暂无阶段证据</div>;
  }
  return (
    <div className="stage-timeline">
      {stages.map((stage) => (
        <button
          key={stage.stage_id}
          className={selectedStageId === stage.stage_id ? "active" : ""}
          type="button"
          onClick={() => onSelect(stage.stage_id)}
          aria-label={`select stage ${stage.phase}`}
        >
          <span>{stage.phase}</span>
          <b>{compactNumber(stage.people.posts)} posts · {compactNumber(stage.people.authors)} authors</b>
          <em className={(stage.price.delta_pct ?? 0) >= 0 ? "up" : "down"}>{formatSignedPercent(stage.price.delta_pct)}</em>
        </button>
      ))}
    </div>
  );
}

function StageInspector({ stage, timeline }: { stage: TokenTimelineStage | null; timeline: TokenSocialTimelineData | null }) {
  if (!stage) {
    return <div className="empty-state">选择一个阶段查看证据</div>;
  }
  const posts = (timeline?.posts ?? []).filter((post) => stage.representative_event_ids.includes(post.event_id));
  return (
    <div className="stage-inspector">
      <dl>
        <div>
          <dt>trigger</dt>
          <dd>{formatReason(stage.trigger_reason)}</dd>
        </div>
        <div>
          <dt>time</dt>
          <dd>{formatRelativeTime(stage.start_ms)}{" -> "}{formatRelativeTime(stage.end_ms)}</dd>
        </div>
        <div>
          <dt>people</dt>
          <dd>{stage.people.watched_posts} watched · top {Math.round(stage.people.top_author_share * 100)}%</dd>
        </div>
        <div>
          <dt>price</dt>
          <dd>{stage.price.status} · {formatSignedPercent(stage.price.delta_pct)}</dd>
        </div>
      </dl>
      <div className="stage-risk-row">
        {stage.risks.length ? stage.risks.map((risk) => <span key={risk}>{formatRisk(risk)}</span>) : <span>no active stage risk</span>}
      </div>
      <div className="stage-posts">
        {posts.map((post) => (
          <article key={post.event_id}>
            <b>@{post.handle ?? "unknown"}</b>
            <p>{eventText({ event_id: post.event_id, text_clean: post.text })}</p>
          </article>
        ))}
        {!posts.length ? <div className="empty-state">该阶段暂无代表帖</div> : null}
      </div>
    </div>
  );
}

function LedgerMetric({ label, value, delta, compact }: { label: string; value?: number | null; delta?: number | null; compact?: boolean }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value === null || value === undefined ? "-" : compact ? compactNumber(value) : formatTokenPriceUsd(value)}</b>
      {delta !== null && delta !== undefined ? <em className={delta >= 0 ? "up" : "down"}>{formatSignedPercent(delta)}</em> : null}
    </div>
  );
}

function priceRelation(token: TokenFlowItem): string {
  if (token.timing.status === "market_pending") {
    return "market pending";
  }
  if (token.timing.chase_risk || token.timing.status === "chase_risk") {
    return "chase risk";
  }
  const change = token.market.price_change_since_social_pct;
  if (change === null || change === undefined) {
    return token.market.price_change_status;
  }
  return `${formatSignedPercent(change)} since social`;
}
