import { formatScore, shortAddress, tokenLabel } from "@lib/format";
import { OBSERVATION_WINDOWS } from "@lib/observationWindows";
import type {
  AccountQualityData,
  TokenDetailMode,
  TokenPostRange,
  TokenPostSortMode,
  TokenDetailTab,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey,
} from "@lib/types";
import { tokenVenueAction } from "@lib/venue";
import {
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell,
  DetailDrawerTagStrip,
} from "@shared/ui/DetailDrawer";
import { RemoteState } from "@shared/ui/RemoteState";
import { ScoreLedger } from "@shared/ui/ScoreLedger";
import { TokenPostsPanel } from "@shared/ui/TokenPostsPanel";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import { ArrowUpRight } from "lucide-react";

import { tokenDrawerSummary } from "../model/TokenRadarRow.model";

import { AccountLane } from "./AccountLane";
import { TokenReplayFocus } from "./TokenReplayFocus";
import { TokenTimeline } from "./TokenTimeline";

const TABS: Array<{ tab: TokenDetailTab; label: string }> = [
  { tab: "timeline", label: "Timeline" },
  { tab: "posts", label: "Posts" },
  { tab: "score", label: "Score" },
  { tab: "lab", label: "Lab" },
  { tab: "accounts", label: "Accounts" },
];

type TokenDetailDrawerProps = {
  token: TokenFlowItem | null;
  activeTab: TokenDetailTab;
  timeline?: TokenSocialTimelineData | null;
  posts?: TokenPostsData | null;
  accountQuality?: AccountQualityData | null;
  isTimelineLoading: boolean;
  isPostsLoading: boolean;
  isPostsFetchingNextPage: boolean;
  isAccountQualityLoading: boolean;
  signalLabLoading: boolean;
  detailWindow: WindowKey;
  detailMode: TokenDetailMode;
  selectedBucketStartMs: number | null;
  selectedEventId: string | null;
  postRange: TokenPostRange;
  postSortMode: TokenPostSortMode;
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  onTabChange: (tab: TokenDetailTab) => void;
  onDetailWindowChange: (window: WindowKey) => void;
  onTimelineBucketSelect: (bucketStartMs: number) => void;
  onBackToTimeline: () => void;
  onSelectedEventChange: (eventId: string | null) => void;
  onPostRangeChange: (range: TokenPostRange) => void;
  onPostSortModeChange: (mode: TokenPostSortMode) => void;
  onHideDuplicateClustersChange: (enabled: boolean) => void;
  onWatchedPostsOnlyChange: (enabled: boolean) => void;
  onLoadMorePosts: () => void;
  onOpenSearchIntel: (token: TokenFlowItem) => void;
};

export function TokenDetailDrawer({
  token,
  activeTab,
  timeline,
  posts,
  accountQuality,
  isTimelineLoading,
  isPostsLoading,
  isPostsFetchingNextPage,
  isAccountQualityLoading,
  signalLabLoading,
  detailWindow,
  detailMode,
  selectedBucketStartMs,
  selectedEventId,
  postRange,
  postSortMode,
  hideDuplicateClusters,
  watchedPostsOnly,
  onTabChange,
  onDetailWindowChange,
  onTimelineBucketSelect,
  onBackToTimeline,
  onSelectedEventChange,
  onPostRangeChange,
  onPostSortModeChange,
  onHideDuplicateClustersChange,
  onWatchedPostsOnlyChange,
  onLoadMorePosts,
  onOpenSearchIntel,
}: TokenDetailDrawerProps) {
  if (!token) {
    return (
      <DetailDrawerShell>
        <DetailDrawerHeader
          badge="-"
          className="select-token-empty"
          eyebrow="selected token"
          subtitle="no token selected"
          title="Select Token"
        />
        <DetailDrawerSection>
          <RemoteState.Empty title="从 Token Radar 或实时信号 Tape 选择一个币" />
        </DetailDrawerSection>
      </DetailDrawerShell>
    );
  }

  const risks = [...(token.opportunity.hard_risks ?? []), ...token.opportunity.risks];
  const drawerSummary = tokenDrawerSummary(token);
  const venueAction = tokenVenueAction(token);
  const headerActions = (
    <div className="drawer-actions">
      <button
        aria-label={`Open Search Intel for ${tokenLabel(token)}`}
        className="drawer-action-link drawer-search-link"
        type="button"
        onClick={() => onOpenSearchIntel(token)}
      >
        <ArrowUpRight aria-hidden />
        Search Intel
      </button>
      {venueAction ? (
        <a
          aria-label={`Open selected token on ${venueAction.label}`}
          className="venue-link drawer-venue-link"
          href={venueAction.url}
          rel="noreferrer"
          target="_blank"
        >
          {venueAction.label}
        </a>
      ) : null}
    </div>
  );
  return (
    <DetailDrawerShell>
      <DetailDrawerHeader
        actions={headerActions}
        badge={formatScore(token.opportunity.score)}
        eyebrow="selected token"
        metrics={
          <DetailDrawerMetricGrid>
            <DetailDrawerMetric label="heat" value={drawerSummary.heat} />
            <DetailDrawerMetric label="quality" value={drawerSummary.quality} />
            <DetailDrawerMetric label="spread" value={drawerSummary.spread} />
            <DetailDrawerMetric label="timing" value={drawerSummary.timing} />
          </DetailDrawerMetricGrid>
        }
        subtitle={
          <>
            {token.identity.chain ?? "unknown"} ·{" "}
            {shortAddress(token.identity.address ?? token.identity.identity_key)} ·{" "}
            {token.identity.identity_status}
          </>
        }
        title={tokenLabel(token)}
      >
        <DetailDrawerTagStrip
          emptyLabel="no active risk flags"
          featuredItem={token.opportunity.decision}
          items={risks.slice(0, 8)}
        />
        <label className="detail-window-control" htmlFor="selected-token-detail-window">
          <span>detail window</span>
          <select
            aria-label="selected token detail window"
            id="selected-token-detail-window"
            value={detailWindow}
            onChange={(event) => onDetailWindowChange(event.target.value as WindowKey)}
          >
            {OBSERVATION_WINDOWS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </DetailDrawerHeader>
      <TokenProfileCard compact profile={token.profile} />

      <nav className="tabs" aria-label="token detail tabs">
        {TABS.map((item) => (
          <button
            key={item.tab}
            className={activeTab === item.tab ? "active" : ""}
            type="button"
            onClick={() => onTabChange(item.tab)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {activeTab === "timeline" ? (
        <DetailDrawerSection>
          {detailMode === "replay" ? (
            <TokenReplayFocus
              isLoading={isTimelineLoading}
              selectedBucketStartMs={selectedBucketStartMs}
              selectedEventId={selectedEventId}
              timeline={timeline}
              onBack={onBackToTimeline}
              onSelectedEventChange={onSelectedEventChange}
            />
          ) : (
            <>
              <div className="section-title">heat timeline · {detailWindow}</div>
              <TokenTimeline
                isLoading={isTimelineLoading}
                selectedBucketStartMs={selectedBucketStartMs}
                timeline={timeline}
                onBucketSelect={onTimelineBucketSelect}
              />
            </>
          )}
        </DetailDrawerSection>
      ) : null}
      {activeTab === "posts" ? (
        <DetailDrawerSection title={<>posts · {detailWindow}</>}>
          <TokenPostsPanel
            hideDuplicateClusters={hideDuplicateClusters}
            isFetchingNextPage={isPostsFetchingNextPage}
            isLoading={isPostsLoading}
            posts={posts}
            postRange={postRange}
            postSortMode={postSortMode}
            watchedPostsOnly={watchedPostsOnly}
            onHideDuplicateClustersChange={onHideDuplicateClustersChange}
            onLoadMorePosts={onLoadMorePosts}
            onPostRangeChange={onPostRangeChange}
            onPostSortModeChange={onPostSortModeChange}
            onWatchedPostsOnlyChange={onWatchedPostsOnlyChange}
          />
        </DetailDrawerSection>
      ) : null}
      {activeTab === "score" ? (
        <DetailDrawerSection title="score ledger">
          <ScoreLedger token={token} />
        </DetailDrawerSection>
      ) : null}
      {activeTab === "lab" ? (
        <DetailDrawerSection title={<>Trading attention · {tokenLabel(token)}</>}>
          {signalLabLoading ? (
            <RemoteState.Loading layout="panel" rows={3} label="loading trading attention" />
          ) : (
            <RemoteState.Empty title="Open Signal Lab to inspect watched-account token, topic, ecosystem, structure, and risk attention." />
          )}
        </DetailDrawerSection>
      ) : null}
      {activeTab === "accounts" ? (
        <DetailDrawerSection title="accounts">
          <AccountLane
            accountQuality={accountQuality}
            isLoading={isAccountQualityLoading}
            timeline={timeline}
          />
        </DetailDrawerSection>
      ) : null}
    </DetailDrawerShell>
  );
}
