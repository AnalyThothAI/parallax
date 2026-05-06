import type {
  AccountQualityData,
  SignalLabChain,
  TokenDetailMode,
  TokenPostRange,
  TokenPostSortMode,
  TokenDetailTab,
  TokenFlowItem,
  TokenPostsData,
  TokenSocialTimelineData,
  WindowKey
} from "../api/types";
import { gmgnTokenUrl } from "../lib/gmgn";
import { formatScore, shortAddress, tokenLabel } from "../lib/format";
import { OBSERVATION_WINDOWS } from "../lib/observationWindows";
import { AccountLane } from "./AccountLane";
import { ScoreLedger } from "./ScoreLedger";
import { SignalChainList } from "./SignalChainList";
import { TokenPostsTab } from "./TokenPostsTab";
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
  signalChains: SignalLabChain[];
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
  onSelectSignalChain: (chain: SignalLabChain) => void;
};

export function TokenDetailDrawer({
  token,
  activeTab,
  timeline,
  posts,
  signalChains,
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
  onLoadMorePosts,
  onSelectSignalChain
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
  const gmgnUrl = gmgnTokenUrl(token.identity.chain, token.identity.address);
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
            {gmgnUrl ? (
              <a aria-label="Open selected token on GMGN" className="gmgn-link drawer-gmgn-link" href={gmgnUrl} rel="noreferrer" target="_blank">
                GMGN
              </a>
            ) : null}
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
        </section>
      ) : null}
      {activeTab === "posts" ? (
        <section className="drawer-section">
          <div className="section-title">posts · {detailWindow}</div>
          <TokenPostsTab
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
        </section>
      ) : null}
      {activeTab === "score" ? (
        <section className="drawer-section">
          <div className="section-title">score ledger</div>
          <ScoreLedger token={token} />
        </section>
      ) : null}
      {activeTab === "lab" ? (
        <section className="drawer-section">
          <div className="section-title">Signal Chains · {tokenLabel(token)}</div>
          <SignalChainList compact isLoading={isSignalLabLoading} items={signalChains} onSelect={onSelectSignalChain} />
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
