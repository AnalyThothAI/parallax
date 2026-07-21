import type {
  WatchlistHandleOverviewData,
  WatchlistHandleRowOverview,
} from "@lib/types";
import * as PageState from "@shared/ui/PageState";
import { useEffect, useMemo } from "react";

import { useHandleOverviewQuery } from "../api/useHandleOverviewQuery";
import { useHandleTimelineQuery } from "../api/useHandleTimelineQuery";
import { useWatchlistHandlesOverviewQuery } from "../api/useWatchlistHandlesOverviewQuery";
import { normalizeWatchlistHandle } from "../model/watchlistCase";
import { buildWatchlistRows, emptyWatchlistHandleRow } from "../model/watchlistRows";
import { useWatchlistRouteState } from "../state/watchlistRouteState";

import { HandleTimeline } from "./HandleTimeline";
import { WatchlistHero } from "./WatchlistHero";
import { WatchlistInsightRail } from "./WatchlistInsightRail";
import { WatchlistMetricStrip } from "./WatchlistMetricStrip";
import { WatchlistSourceNavigator } from "./WatchlistSourceNavigator";
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
  const handlesOverviewQuery = useWatchlistHandlesOverviewQuery({ token });
  const overviewQuery = useHandleOverviewQuery({
    handle: selectedHandle,
    token,
  });
  const timelineQuery = useHandleTimelineQuery({
    handle: selectedHandle,
    token,
  });
  const overview = overviewQuery.data?.data ?? null;
  const selectedUnreadCount = Number(accountUnreadCounts?.[selectedHandle ?? ""] ?? 0);
  const sourceRows = useMemo(
    () =>
      buildWatchlistRows({
        accountUnreadCounts,
        rows: mergeConfiguredHandleRows(
          normalizedHandles,
          handlesOverviewQuery.data?.data.items ?? [],
        ),
      }),
    [accountUnreadCounts, handlesOverviewQuery.data?.data.items, normalizedHandles],
  );

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
        <div className="watchlist-desk-layout">
          <WatchlistSourceNavigator
            overviewWindow={handlesOverviewQuery.data?.data.window ?? null}
            rows={sourceRows}
            selectedHandle={selectedHandle}
            updating={handlesOverviewQuery.isFetching}
          />
          <div className="watchlist-dossier">
            <WatchlistMetricStrip
              metrics={overview?.metrics ?? null}
              unreadCount={selectedUnreadCount}
            />
            {overviewQuery.isError ? (
              <PageState.Error
                error={overviewQuery.error}
                onRetry={() => overviewQuery.refetch()}
              />
            ) : null}
            <div className="watchlist-monitor-grid">
              <section
                className="watchlist-evidence-panel"
                aria-labelledby="watchlist-evidence-title"
              >
                <div className="watchlist-section-head">
                  <span>source timeline</span>
                  <h3 id="watchlist-evidence-title">Handle intelligence</h3>
                  <p>{timelineLeadCopy(overview)}</p>
                </div>
                <HandleTimeline query={timelineQuery} />
              </section>

              <WatchlistInsightRail
                candidateClusters={overview?.candidate_mention_clusters ?? []}
                narrativeClusters={overview?.narrative_clusters ?? []}
                resolvedClusters={overview?.resolved_token_clusters ?? []}
                riskNotes={overview?.risk_notes ?? []}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function timelineLeadCopy(overview: WatchlistHandleOverviewData | null): string {
  const count = overview?.metrics.source_event_count ?? 0;
  if (count > 0) {
    return `${count} source events`;
  }
  return "Raw source stream.";
}

function mergeConfiguredHandleRows(
  configuredHandles: string[],
  overviewRows: WatchlistHandleRowOverview[],
): WatchlistHandleRowOverview[] {
  const rowsByHandle = new Map(
    overviewRows
      .map((row) => [normalizeWatchlistHandle(row.handle), row] as const)
      .filter((entry): entry is readonly [string, WatchlistHandleRowOverview] => Boolean(entry[0])),
  );
  const merged = configuredHandles.map(
    (handle) => rowsByHandle.get(handle) ?? emptyWatchlistHandleRow(handle),
  );
  const configured = new Set(configuredHandles);
  for (const row of overviewRows) {
    const normalized = normalizeWatchlistHandle(row.handle);
    if (normalized && !configured.has(normalized)) {
      merged.push(row);
    }
  }
  return merged;
}
