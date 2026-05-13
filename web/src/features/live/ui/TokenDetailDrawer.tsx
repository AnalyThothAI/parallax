import { formatRisk } from "@lib/format";
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
import { DetailDrawerSection, DetailDrawerShell } from "@shared/ui/DetailDrawer";
import { RemoteState } from "@shared/ui/RemoteState";
import { ScoreLedger } from "@shared/ui/ScoreLedger";
import { TokenPostsPanel } from "@shared/ui/TokenPostsPanel";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import {
  ObsidianActionBar,
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianEvidenceList,
  ObsidianFieldGrid,
  ObsidianPill,
  ObsidianSection,
  ObsidianTokenMark,
} from "@shared/ui/obsidian";
import { ArrowUpRight } from "lucide-react";

import { buildTokenCaseView } from "../model/tokenCase";

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
        <ObsidianCase aria-label="selected case" className="selected-case-file">
          <ObsidianCaseHeader
            badge={<ObsidianPill>empty</ObsidianPill>}
            eyebrow="selected case"
            mark={<ObsidianTokenMark label="?" tone="neutral" />}
            subtitle="No token case selected."
            title="Select Case"
          />
        </ObsidianCase>
        <DetailDrawerSection title="next action">
          <RemoteState.Empty title="从 Token Radar 或实时信号 Tape 选择一个币" />
        </DetailDrawerSection>
      </DetailDrawerShell>
    );
  }

  const risks = [...(token.opportunity.hard_risks ?? []), ...token.opportunity.risks];
  const tokenCase = buildTokenCaseView(token);
  const venueAction = tokenVenueAction(token);
  const headerActions = (
    <ObsidianActionBar className="drawer-actions">
      <button
        aria-label={`Open Search Intel for ${tokenCase.label}`}
        className="drawer-action-link drawer-search-link"
        type="button"
        onClick={() => onOpenSearchIntel(token)}
      >
        <ArrowUpRight aria-hidden />
        Search Intel
      </button>
      {venueAction ? (
        <a
          aria-label={`Open selected case on ${venueAction.label}`}
          className="venue-link drawer-venue-link"
          href={venueAction.url}
          rel="noreferrer"
          target="_blank"
        >
          {venueAction.label}
        </a>
      ) : null}
    </ObsidianActionBar>
  );
  const evidenceItems = [
    ...tokenCase.evidence.map((reason, index) => ({
      body: reason,
      id: `reason-${index}`,
      title: "Decision rationale",
      tone: tokenCase.decision.tone,
    })),
    ...risks.slice(0, 6).map((risk, index) => ({
      body: formatRisk(risk),
      id: `risk-${index}`,
      title: "Risk flag",
      tone: "risk" as const,
    })),
  ];

  return (
    <DetailDrawerShell>
      <ObsidianCase aria-label={`Selected case ${tokenCase.label}`} className="selected-case-file">
        <ObsidianCaseHeader
          actions={headerActions}
          badge={
            <ObsidianPill tone={tokenCase.decision.tone}>
              {tokenCase.decision.value} · {tokenCase.score}
            </ObsidianPill>
          }
          eyebrow="selected case"
          lead={tokenCase.evidence[0] ?? tokenCase.decision.detail}
          mark={<ObsidianTokenMark label={tokenCase.label} tone={tokenCase.decision.tone} />}
          subtitle={tokenCase.subtitle}
          title={tokenCase.label}
        />

        <ObsidianSection
          subtitle="Official facts, community proof, narrative, market and decision share one file."
          title="Primary file"
        >
          <ObsidianFieldGrid
            fields={[
              tokenCase.identity,
              tokenCase.official,
              tokenCase.community,
              tokenCase.narrative,
              tokenCase.market,
              tokenCase.decision,
            ]}
          />
        </ObsidianSection>

        <ObsidianSection
          subtitle="Persisted profile facts remain separate from agent or deterministic narrative."
          title="Official profile"
        >
          <TokenProfileCard compact profile={token.profile} />
        </ObsidianSection>

        <ObsidianSection title="Evidence">
          <ObsidianEvidenceList
            emptyLabel="No decision evidence or risk flags in this window."
            items={evidenceItems}
          />
        </ObsidianSection>

        <ObsidianSection title="Evidence window">
          <label className="detail-window-control" htmlFor="selected-case-detail-window">
            <span>window</span>
            <select
              aria-label="selected case evidence window"
              id="selected-case-detail-window"
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
        </ObsidianSection>
      </ObsidianCase>

      <DetailDrawerSection title="secondary evidence">
        <nav className="tabs" aria-label="selected case evidence views">
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
      </DetailDrawerSection>

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
              <div className="section-title">case timeline · {detailWindow}</div>
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
        <DetailDrawerSection title={<>Trading attention · {tokenCase.label}</>}>
          {signalLabLoading ? (
            <RemoteState.Loading layout="panel" rows={3} label="loading trading attention" />
          ) : (
            <RemoteState.Empty title="Open Signal Pulse to inspect watched-account token, topic, ecosystem, structure, and risk attention." />
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
