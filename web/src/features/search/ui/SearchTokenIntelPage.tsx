import { compactNumber, formatPropagationPhase, formatScore, shortAddress } from "@lib/format";
import type { SearchInspectData, SearchTargetCandidate, SearchTokenResult } from "@lib/types";
import { TokenIntelHeader } from "@shared/ui/TokenIntelHeader";
import { ObsidianPill, ObsidianTokenMark } from "@shared/ui/case-file";
import { useMemo, useState } from "react";

import { buildSearchCaseView } from "../model/searchCase";
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
  const tokenCase = useMemo(() => buildSearchCaseView(data), [data]);
  const radar = useMemo(() => buildSearchRadarSummary(result), [result]);
  const title = tokenTitle(result);
  const caseLabel = tokenCaseLabel(result);
  const subtitle = targetIdentityLine(result.target, result.market_overlay);
  const radarTone = radar.radarStatusLabel === "radar row" ? "info" : "neutral";
  const marketTone = radar.primaryMarketTone === "positive" ? "health" : "neutral";

  return (
    <div className="search-content search-token-intel">
      <TokenIntelHeader
        actions={<SearchIntelControls routeState={routeState} onRouteChange={onRouteChange} />}
        ariaLabel={`Search case ${caseLabel}`}
        badge={
          <ObsidianPill tone={radarTone}>{radar.decision || radar.radarStatusLabel}</ObsidianPill>
        }
        className="search-token-case"
        eyebrow="token intelligence"
        fields={[
          tokenCase.official,
          tokenCase.community,
          {
            detail: radar.primaryMarketDetail,
            label: radar.primaryMarketLabel,
            source: "market",
            tone: marketTone,
            value: radar.primaryMarketValue,
          },
          {
            detail: `${radar.dataHealthLine} · ${radar.gateLine}`,
            label: "Radar",
            source: "deterministic",
            tone: radarTone,
            value: radar.rankScore
              ? `${formatScore(radar.rankScore)} / 100`
              : radar.radarStatusLabel,
          },
          {
            detail: result.agent_brief.project_summary.one_liner,
            label: "Narrative",
            source: "agent",
            tone: "agent",
            value: formatPropagationPhase(result.timeline.summary.phase),
          },
          {
            detail: `${compactNumber(result.posts.total_count)} total · ${
              selectedStageId === "all" ? "all stages" : selectedStageId
            }`,
            label: "Evidence",
            source: "social",
            tone: result.posts.returned_count ? "health" : "neutral",
            value: `${compactNumber(result.posts.returned_count)} shown`,
          },
        ]}
        mark={<ObsidianTokenMark label={caseLabel} tone={radarTone} />}
        meta={
          <div className="search-token-meta">
            <code>{result.target.target_type}</code>
            <code>{result.target.status}</code>
            <code>{data.query.window}</code>
            <code>{data.query.scope}</code>
          </div>
        }
        profile={result.profile}
        profileLabel={`Token intelligence for ${plainSymbol(title)}`}
        subtitle={subtitle}
        title={title}
      />

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
