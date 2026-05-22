import type { WatchlistHandleOverviewData, WatchlistTimelineScope } from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { useEffect, useMemo } from "react";

import { useHandleOverviewQuery } from "../api/useHandleOverviewQuery";
import { useHandleSummaryQuery } from "../api/useHandleSummaryQuery";
import { useHandleTimelineQuery } from "../api/useHandleTimelineQuery";
import { normalizeWatchlistHandle } from "../model/watchlistCase";
import { useWatchlistRouteState } from "../state/watchlistRouteState";

import { HandleTimeline } from "./HandleTimeline";
import { HandleTopicSummary } from "./HandleTopicSummary";
import { WatchlistHero } from "./WatchlistHero";
import { WatchlistInsightRail } from "./WatchlistInsightRail";
import { WatchlistMetricStrip } from "./WatchlistMetricStrip";
import "./watchlist.css";
import "./watchlistResponsive.css";

type WatchlistPageProps = {
  accountUnreadCounts?: Record<string, number> | null;
  handles: string[];
  onMarkHandleRead?: (handle: string) => void;
  token: string;
};

export function WatchlistPage({
  accountUnreadCounts,
  handles,
  onMarkHandleRead,
  token,
}: WatchlistPageProps) {
  const normalizedHandles = useMemo(
    () =>
      handles
        .map((handle) => normalizeWatchlistHandle(handle))
        .filter((handle): handle is string => Boolean(handle)),
    [handles],
  );
  const routeState = useWatchlistRouteState(normalizedHandles[0] ?? null);
  const selectedHandle = routeState.selectedHandle;
  const timelineScope = routeState.timelineScope;
  const overviewQuery = useHandleOverviewQuery({
    handle: selectedHandle,
    scope: timelineScope,
    token,
  });
  const summaryQuery = useHandleSummaryQuery({ handle: selectedHandle, token });
  const timelineQuery = useHandleTimelineQuery({
    handle: selectedHandle,
    scope: timelineScope,
    token,
  });
  const overview = overviewQuery.data?.data ?? null;
  const selectedUnreadCount = Number(accountUnreadCounts?.[selectedHandle ?? ""] ?? 0);

  useEffect(() => {
    if (!selectedHandle || selectedUnreadCount <= 0) {
      return;
    }
    onMarkHandleRead?.(selectedHandle);
  }, [onMarkHandleRead, selectedHandle, selectedUnreadCount]);

  if (!selectedHandle) {
    return (
      <section className="watchlist-page" aria-label="Watchlist">
        <PageState.Empty title="No watchlist handles configured." />
      </section>
    );
  }

  return (
    <section className="watchlist-page" aria-label="Twitter source monitor">
      <div className="watchlist-monitor-shell">
        <WatchlistHero
          handle={selectedHandle}
          lastSeenAtMs={overview?.metrics.last_source_event_at_ms ?? null}
        />
        <WatchlistMetricStrip
          metrics={overview?.metrics ?? null}
          unreadCount={selectedUnreadCount}
        />
        {overviewQuery.isError ? (
          <PageState.Error error={overviewQuery.error} onRetry={() => overviewQuery.refetch()} />
        ) : null}
        <HandleTopicSummary query={summaryQuery} />
        <div className="watchlist-monitor-grid">
          <section className="watchlist-evidence-panel" aria-labelledby="watchlist-evidence-title">
            <div className="watchlist-section-head">
              <span>source timeline</span>
              <h3 id="watchlist-evidence-title">Handle intelligence</h3>
              <p>{timelineLeadCopy(timelineScope, overview)}</p>
            </div>
            <HandleTimeline
              query={timelineQuery}
              scope={timelineScope}
              onScopeChange={routeState.updateTimelineScope}
            />
          </section>

          <WatchlistInsightRail
            candidateClusters={overview?.candidate_mention_clusters ?? []}
            narrativeClusters={overview?.narrative_clusters ?? []}
            resolvedClusters={overview?.resolved_token_clusters ?? []}
            riskNotes={overview?.risk_notes ?? []}
          />
        </div>
      </div>
    </section>
  );
}

function timelineLeadCopy(
  scope: WatchlistTimelineScope,
  overview: WatchlistHandleOverviewData | null,
): string {
  const count = overview?.metrics.source_event_count ?? 0;
  if (count > 0) {
    return scope === "signal" ? `${count} structured signals` : `${count} source events`;
  }
  return scope === "signal" ? "Structured social-event output." : "Raw source stream.";
}
