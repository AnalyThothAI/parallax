import {
  compactNumber,
  formatPercentShare,
  formatPropagationPhase,
  formatScore,
  shortAddress,
} from "@lib/format";
import type { SearchInspectData, SearchTargetCandidate, SearchTokenResult } from "@lib/types";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import { useMemo, useState } from "react";

import { buildSearchRadarSummary } from "../model/searchRadar";
import type { SearchRouteState } from "../state/searchRouteState";

import { SearchAgentBrief } from "./SearchAgentBrief";
import { SearchIntelControls } from "./SearchIntelControls";
import { SearchRadarPanel } from "./SearchRadarPanel";
import { SearchTimelinePanel } from "./SearchTimelinePanel";
import { SearchTwitterResults } from "./SearchTwitterResults";

type SearchTokenIntelPageProps = {
  data: SearchInspectData;
  result: SearchTokenResult;
  routeState: SearchRouteState;
  onRouteChange: (patch: Partial<SearchRouteState>) => void;
};

export function SearchTokenIntelPage({
  data,
  result,
  routeState,
  onRouteChange,
}: SearchTokenIntelPageProps) {
  const [selectedStageId, setSelectedStageId] = useState<string>("all");
  const radar = useMemo(() => buildSearchRadarSummary(result), [result]);
  const title = tokenTitle(result);
  const caseLabel = tokenCaseLabel(result);
  const subtitle = targetIdentityLine(result.target, result.market_overlay);
  const narrative = result.agent_brief.project_summary.one_liner;

  return (
    <div className="search-content search-token-intel">
      <section className="search-token-hero" aria-label={`Search case ${caseLabel}`}>
        <div className="search-token-identity">
          <span>token intelligence</span>
          <h3>{title}</h3>
          <p>{subtitle}</p>
          <div className="search-token-meta">
            <code>{result.target.target_type}</code>
            <code>{result.target.status}</code>
            <code>{data.query.window}</code>
            <code>{data.query.scope}</code>
          </div>
        </div>

        <div className="search-token-action-block">
          <div className="search-token-decision">
            <span>decision</span>
            <b>{radar.decision || result.agent_brief.bull_bear.stance}</b>
            <small>
              {radar.rankScore ? `${formatScore(radar.rankScore)} / 100` : radar.radarStatusLabel}
            </small>
          </div>
          <SearchIntelControls routeState={routeState} onRouteChange={onRouteChange} />
        </div>
      </section>

      <div
        className="search-token-profile-row"
        role="region"
        aria-label={`Token intelligence for ${plainSymbol(title)}`}
      >
        <TokenProfileCard profile={result.profile} />
      </div>

      <section className="search-token-decision-strip" aria-label="Token decision summary">
        <SummaryTile
          label="social proof"
          value={`${compactNumber(result.timeline.summary.posts)} posts`}
          detail={`${compactNumber(result.timeline.summary.authors)} authors · watched ${compactNumber(
            result.timeline.summary.watched_posts ?? 0,
          )} · top ${formatPercentShare(result.timeline.summary.top_author_share)}`}
        />
        <SummaryTile
          label={radar.primaryMarketLabel}
          value={radar.primaryMarketValue}
          detail={radar.primaryMarketDetail}
        />
        <SummaryTile
          label="narrative"
          value={formatPropagationPhase(result.timeline.summary.phase)}
          detail={narrative}
        />
        <SummaryTile
          label="data health"
          value={radar.marketHealth}
          detail={`${radar.dataHealthLine} · ${radar.gateLine}`}
        />
        <SummaryTile
          label="evidence"
          value={`${compactNumber(result.posts.returned_count)} shown`}
          detail={`${compactNumber(result.posts.total_count)} total · ${selectedStageId === "all" ? "all stages" : selectedStageId}`}
        />
      </section>

      <div className="search-content-grid">
        <div className="search-primary-stack">
          <SearchTimelinePanel
            activeStageId={selectedStageId}
            marketOverlay={result.market_overlay}
            timeline={result.timeline}
            onStageSelect={setSelectedStageId}
          />
          <SearchTwitterResults
            selectedStageId={selectedStageId}
            title={`${data.query.window} Evidence Stream`}
            posts={result.posts.items}
            hasMore={result.posts.has_more}
            onSelectedStageChange={setSelectedStageId}
          />
        </div>
        <div className="search-insight-stack">
          <SearchAgentBrief brief={result.agent_brief} />
          <SearchRadarPanel summary={radar} />
        </div>
      </div>
    </div>
  );
}

function SummaryTile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
      <em>{detail}</em>
    </div>
  );
}

function tokenTitle(result: SearchTokenResult): string {
  const identity = result.profile?.identity;
  const symbol = cleanText(identity?.symbol) ?? cleanText(result.target.symbol);
  const name = cleanText(identity?.name);
  if (symbol && name && name.toLowerCase() !== symbol.toLowerCase()) {
    return `$${symbol} · ${name}`;
  }
  if (symbol) {
    return `$${symbol}`;
  }
  return shortTarget(result.target.target_id);
}

function tokenCaseLabel(result: SearchTokenResult): string {
  const symbol = cleanText(result.profile?.identity?.symbol) ?? cleanText(result.target.symbol);
  return symbol ? `$${symbol}` : shortTarget(result.target.target_id);
}

function targetIdentityLine(
  candidate: SearchTargetCandidate,
  marketOverlay: Record<string, unknown>,
) {
  const chain = candidate.chain_id ?? stringValue(marketOverlay.chain_id);
  const address = candidate.address ?? stringValue(marketOverlay.address);
  const nativeMarket = stringValue(marketOverlay.native_market_id);
  if (candidate.target_type === "CexToken" && nativeMarket !== "-") {
    return `${nativeMarket} · ${candidate.target_id}`;
  }
  if (address && address !== "-") {
    return `${chain || "chain"} · ${shortAddress(address)}`;
  }
  return candidate.target_id;
}

function plainSymbol(value: string): string {
  return value.replace(/^\$/, "").split(" · ")[0] || value;
}

function shortTarget(value: string) {
  return value.length > 28 ? `${value.slice(0, 14)}...${value.slice(-8)}` : value;
}

function cleanText(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function stringValue(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "-";
}
