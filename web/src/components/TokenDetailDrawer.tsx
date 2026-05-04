import type {
  AccountQualityData,
  AttentionFrontierItem,
  Decision,
  NarrativeFlowItem,
  TimelineBucket,
  TokenDetailTab,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData
} from "../api/types";
import {
  compactNumber,
  formatPercentShare,
  formatRisk,
  formatScore,
  formatSignedPercent,
  formatTimingStatus,
  formatUsdCompact,
  shortAddress,
  tokenLabel
} from "../lib/format";
import { AccountLane } from "./AccountLane";
import { DecisionTag } from "./DecisionTag";
import { NarrativePanel } from "./NarrativePanel";
import { ScoreLedger } from "./ScoreLedger";
import { TokenPostsTab } from "./TokenPostsTab";
import { TokenTimeline } from "./TokenTimeline";

const TABS: Array<{ tab: TokenDetailTab; label: string }> = [
  { tab: "timeline", label: "Timeline" },
  { tab: "posts", label: "Posts" },
  { tab: "score", label: "Score" },
  { tab: "narratives", label: "Narratives" },
  { tab: "accounts", label: "Accounts" }
];

type TokenDetailDrawerProps = {
  token: TokenFlowItem | null;
  activeTab: TokenDetailTab;
  manualDecision?: Decision;
  timeline?: TokenSocialTimelineData | null;
  posts?: TokenPostsData | null;
  narratives: NarrativeFlowItem[];
  narrativeLinks: AttentionFrontierItem[];
  accountQuality?: AccountQualityData | null;
  isTimelineLoading: boolean;
  isPostsLoading: boolean;
  isPostsFetchingNextPage: boolean;
  isAccountQualityLoading: boolean;
  timelineBucket: TimelineBucket;
  postSortMode: "recent" | "quality";
  hideDuplicateClusters: boolean;
  watchedPostsOnly: boolean;
  llmConfigured: boolean;
  onTabChange: (tab: TokenDetailTab) => void;
  onDecisionOverride: (decision: Decision) => void;
  onTimelineBucketChange: (bucket: TimelineBucket) => void;
  onPostSortModeChange: (mode: "recent" | "quality") => void;
  onHideDuplicateClustersChange: (enabled: boolean) => void;
  onWatchedPostsOnlyChange: (enabled: boolean) => void;
  onLoadMorePosts: () => void;
};

export function TokenDetailDrawer({
  token,
  activeTab,
  manualDecision,
  timeline,
  posts,
  narratives,
  narrativeLinks,
  accountQuality,
  isTimelineLoading,
  isPostsLoading,
  isPostsFetchingNextPage,
  isAccountQualityLoading,
  timelineBucket,
  postSortMode,
  hideDuplicateClusters,
  watchedPostsOnly,
  llmConfigured,
  onTabChange,
  onDecisionOverride,
  onTimelineBucketChange,
  onPostSortModeChange,
  onHideDuplicateClustersChange,
  onWatchedPostsOnlyChange,
  onLoadMorePosts
}: TokenDetailDrawerProps) {
  if (!token) {
    return (
      <aside className="detail-drawer">
        <section className="detail-focus select-token-empty">
          <header className="drawer-head">
            <div>
              <h2>Select Token</h2>
              <span>右侧详情组件已保留</span>
            </div>
          </header>
          <div className="empty-state">从 Token Radar 或实时信号 Tape 选择一个币，查看完整传播时间线、全量帖子、分数账本和账号 lane。</div>
        </section>
      </aside>
    );
  }

  const decision = manualDecision ?? token.opportunity.decision;
  const risks = [...(token.opportunity.hard_risks ?? []), ...token.opportunity.risks];
  return (
    <aside className="detail-drawer">
      <section className="detail-focus">
        <header className="drawer-head">
          <div>
            <h2>{tokenLabel(token)}</h2>
            <span>
              {token.identity.chain ?? "unknown"} · {shortAddress(token.identity.address ?? token.identity.identity_key)}
            </span>
          </div>
          <DecisionTag decision={decision} manual={Boolean(manualDecision)} />
        </header>

        <section className="drawer-hero">
          <div>
            <span>Opportunity</span>
            <b>{formatScore(token.opportunity.score)}</b>
          </div>
          <div>
            <span>Heat</span>
            <b>{formatScore(token.social_heat.score)}</b>
          </div>
          <div>
            <span>Posts</span>
            <b>{compactNumber(token.evidence_total_count)}</b>
          </div>
          <div>
            <span>MCap</span>
            <b>{formatUsdCompact(token.market.market_cap)}</b>
          </div>
        </section>

        <div className="drawer-kv">
          <div>
            <span>delta</span>
            <b>{formatSignedPercent(token.market.price_change_window_pct)}</b>
          </div>
          <div>
            <span>timing</span>
            <b>{formatTimingStatus(token.timing.status)}</b>
          </div>
          <div>
            <span>authors</span>
            <b>{compactNumber(token.propagation.independent_authors)}</b>
          </div>
          <div>
            <span>top share</span>
            <b>{formatPercentShare(token.propagation.top_author_share)}</b>
          </div>
        </div>

        <div className="decision-controls" aria-label="manual token decision override">
          {(["driver", "watch", "discard"] as Decision[]).map((item) => (
            <button key={item} className={decision === item ? "active" : ""} type="button" onClick={() => onDecisionOverride(item)}>
              {item === "driver" ? "D" : item === "watch" ? "W" : "X"} · {item}
            </button>
          ))}
        </div>

        {risks.length ? (
          <div className="risk-strip">
            {risks.slice(0, 8).map((risk) => (
              <span key={risk}>{formatRisk(risk)}</span>
            ))}
          </div>
        ) : null}

        <nav className="focus-tabs" aria-label="token detail tabs">
          {TABS.map((item) => (
            <button key={item.tab} className={activeTab === item.tab ? "active" : ""} type="button" onClick={() => onTabChange(item.tab)}>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="drawer-tab-body">
          {activeTab === "timeline" ? (
            <TokenTimeline
              bucket={timelineBucket}
              isLoading={isTimelineLoading}
              timeline={timeline}
              onBucketChange={onTimelineBucketChange}
            />
          ) : null}
          {activeTab === "posts" ? (
            <TokenPostsTab
              hideDuplicateClusters={hideDuplicateClusters}
              isFetchingNextPage={isPostsFetchingNextPage}
              isLoading={isPostsLoading}
              posts={posts}
              postSortMode={postSortMode}
              watchedPostsOnly={watchedPostsOnly}
              onHideDuplicateClustersChange={onHideDuplicateClustersChange}
              onLoadMorePosts={onLoadMorePosts}
              onPostSortModeChange={onPostSortModeChange}
              onWatchedPostsOnlyChange={onWatchedPostsOnlyChange}
            />
          ) : null}
          {activeTab === "score" ? <ScoreLedger token={token} /> : null}
          {activeTab === "narratives" ? (
            <NarrativePanel
              frontierItems={narrativeLinks}
              llmConfigured={llmConfigured}
              narratives={narratives}
              token={token}
            />
          ) : null}
          {activeTab === "accounts" ? (
            <AccountLane
              accountQuality={accountQuality}
              isLoading={isAccountQualityLoading}
              timeline={timeline}
            />
          ) : null}
        </div>
      </section>
    </aside>
  );
}
