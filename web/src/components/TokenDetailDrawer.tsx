import type {
  AccountQualityData,
  TokenDetailMode,
  TokenPostRange,
  TokenPostSortMode,
  TokenDetailTab,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey
} from "../api/types";
import { formatScore, shortAddress, tokenLabel } from "../lib/format";
import { OBSERVATION_WINDOWS } from "../lib/observationWindows";
import { tokenVenueAction } from "../lib/venue";
import { AccountLane } from "./AccountLane";
import {
  DetailDrawerHeader,
  DetailDrawerMetric,
  DetailDrawerMetricGrid,
  DetailDrawerSection,
  DetailDrawerShell,
  DetailDrawerTagStrip
} from "./DetailDrawer";
import { ScoreLedger } from "./ScoreLedger";
import { TokenPostsPanel } from "./TokenPostsPanel";
import { TokenReplayFocus } from "./TokenReplayFocus";
import { tokenDrawerSummary } from "./TokenRadarRow";
import { TokenTimeline } from "./TokenTimeline";

const TABS: Array<{ tab: TokenDetailTab; label: string }> = [
  { tab: "timeline", label: "Timeline" },
  { tab: "posts", label: "Posts" },
  { tab: "score", label: "Score" },
  { tab: "lab", label: "Lab" },
  { tab: "accounts", label: "Accounts" }
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
  isSignalLabLoading: boolean;
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
  isSignalLabLoading,
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
  onLoadMorePosts
}: TokenDetailDrawerProps) {
  if (!token) {
    return (
      <DetailDrawerShell>
        <DetailDrawerHeader badge="-" className="select-token-empty" eyebrow="selected token" subtitle="no token selected" title="Select Token" />
        <DetailDrawerSection>
          <div className="empty-state">从 Token Radar 或实时信号 Tape 选择一个币</div>
        </DetailDrawerSection>
      </DetailDrawerShell>
    );
  }

  const risks = [...(token.opportunity.hard_risks ?? []), ...token.opportunity.risks];
  const drawerSummary = tokenDrawerSummary(token);
  const venueAction = tokenVenueAction(token);
  return (
    <DetailDrawerShell>
      <DetailDrawerHeader
        actions={
          venueAction ? (
            <a aria-label={`Open selected token on ${venueAction.label}`} className="venue-link drawer-venue-link" href={venueAction.url} rel="noreferrer" target="_blank">
              {venueAction.label}
            </a>
          ) : null
        }
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
            {token.identity.chain ?? "unknown"} · {shortAddress(token.identity.address ?? token.identity.identity_key)} · {token.identity.identity_status}
          </>
        }
        title={tokenLabel(token)}
      >
        <DetailDrawerTagStrip emptyLabel="no active risk flags" featuredItem={token.opportunity.decision} items={risks.slice(0, 8)} />
        <label className="detail-window-control">
          <span>detail window</span>
          <select
            aria-label="selected token detail window"
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

      <nav className="tabs" aria-label="token detail tabs">
        {TABS.map((item) => (
          <button key={item.tab} className={activeTab === item.tab ? "active" : ""} type="button" onClick={() => onTabChange(item.tab)}>
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
          {isSignalLabLoading ? (
            <div className="empty-state">loading trading attention</div>
          ) : (
            <div className="empty-state">Open Signal Lab to inspect watched-account token, topic, ecosystem, structure, and risk attention.</div>
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
