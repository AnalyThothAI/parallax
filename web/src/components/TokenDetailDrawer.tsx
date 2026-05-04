import type {
  AccountQualityData,
  AttentionFrontierItem,
  NarrativeFlowItem,
  TimelineBucket,
  TokenDetailTab,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData
} from "../api/types";
import { formatScore, shortAddress, tokenLabel } from "../lib/format";
import { AccountLane } from "./AccountLane";
import { NarrativePanel } from "./NarrativePanel";
import { ScoreLedger } from "./ScoreLedger";
import { TokenPostsTab } from "./TokenPostsTab";
import { tokenDrawerSummary } from "./TokenRadarRow";
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
  onTimelineBucketChange: (bucket: TimelineBucket) => void;
  onPostSortModeChange: (mode: "recent" | "quality") => void;
  onHideDuplicateClustersChange: (enabled: boolean) => void;
  onWatchedPostsOnlyChange: (enabled: boolean) => void;
  onLoadMorePosts: () => void;
};

export function TokenDetailDrawer({
  token,
  activeTab,
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
  onTimelineBucketChange,
  onPostSortModeChange,
  onHideDuplicateClustersChange,
  onWatchedPostsOnlyChange,
  onLoadMorePosts
}: TokenDetailDrawerProps) {
  if (!token) {
    return (
      <aside className="detail-drawer drawer">
        <header className="drawer-head select-token-empty">
          <div className="drawer-title">
            <div>
              <div className="eyebrow">selected token</div>
              <h2>Select Token</h2>
              <p>no token selected</p>
            </div>
            <div className="opportunity-score">-</div>
          </div>
        </header>
        <section className="drawer-section">
          <div className="empty-state">从 Token Radar 或实时信号 Tape 选择一个币</div>
        </section>
      </aside>
    );
  }

  const risks = [...(token.opportunity.hard_risks ?? []), ...token.opportunity.risks];
  const drawerSummary = tokenDrawerSummary(token);
  return (
    <aside className="detail-drawer drawer">
      <header className="drawer-head">
        <div className="drawer-title">
          <div>
            <div className="eyebrow">selected token</div>
            <h2>{tokenLabel(token)}</h2>
            <p>
              {token.identity.chain ?? "unknown"} · {shortAddress(token.identity.address ?? token.identity.identity_key)} · {token.identity.identity_status}
            </p>
          </div>
          <div className="opportunity-score">{formatScore(token.opportunity.score)}</div>
        </div>

        <div className="drawer-kv">
          <div>
            <span>heat</span>
            <b>{drawerSummary.heat}</b>
          </div>
          <div>
            <span>quality</span>
            <b>{drawerSummary.quality}</b>
          </div>
          <div>
            <span>spread</span>
            <b>{drawerSummary.spread}</b>
          </div>
          <div>
            <span>timing</span>
            <b>{drawerSummary.timing}</b>
          </div>
        </div>

        <div className="risk-strip">
          <span className="hot">{token.opportunity.decision}</span>
          {risks.slice(0, 8).map((risk) => (
            <span key={risk}>{risk}</span>
          ))}
        </div>
      </header>

      <nav className="tabs" aria-label="token detail tabs">
        {TABS.map((item) => (
          <button key={item.tab} className={activeTab === item.tab ? "active" : ""} type="button" onClick={() => onTabChange(item.tab)}>
            {item.label}
          </button>
        ))}
      </nav>

      {activeTab === "timeline" ? (
        <section className="drawer-section">
          <div className="section-title">social timeline · {token.timeline_query.window} bucket={timelineBucket}</div>
            <TokenTimeline
              bucket={timelineBucket}
              isLoading={isTimelineLoading}
              timeline={timeline}
              onBucketChange={onTimelineBucketChange}
            />
        </section>
      ) : null}
      {activeTab === "posts" ? (
        <section className="drawer-section">
          <div className="section-title">top posts</div>
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
        </section>
      ) : null}
      {activeTab === "score" ? (
        <section className="drawer-section">
          <div className="section-title">score ledger</div>
          <ScoreLedger token={token} />
        </section>
      ) : null}
      {activeTab === "narratives" ? (
        <section className="drawer-section">
          <div className="section-title">中文叙事</div>
            <NarrativePanel
              frontierItems={narrativeLinks}
              llmConfigured={llmConfigured}
              narratives={narratives}
              token={token}
            />
        </section>
      ) : null}
      {activeTab === "accounts" ? (
        <section className="drawer-section">
          <div className="section-title">accounts</div>
            <AccountLane
              accountQuality={accountQuality}
              isLoading={isAccountQualityLoading}
              timeline={timeline}
            />
        </section>
      ) : null}
    </aside>
  );
}
