import { formatRelativeTime } from "@lib/format";
import type { WatchlistTimelineScope } from "@lib/types";
import { AtSign, Bell, Radio, SignalHigh } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { WatchlistRow } from "../model/watchlistRows";

import "./WatchlistSourceNavigator.css";

export function WatchlistSourceNavigator({
  overviewWindow,
  rows,
  selectedHandle,
  timelineScope,
  updating,
}: {
  overviewWindow: string | null;
  rows: WatchlistRow[];
  selectedHandle: string | null;
  timelineScope: WatchlistTimelineScope;
  updating: boolean;
}) {
  const totals = sourceTotals(rows);
  const maxActivity = Math.max(...rows.map((row) => row.activityScore), 1);

  return (
    <aside className="watchlist-source-panel" aria-label="Twitter source desk">
      <div className="watchlist-source-head">
        <span>
          <Radio aria-hidden />
          source desk
        </span>
        <h3>Twitter list</h3>
        <p>
          {overviewWindow
            ? `${overviewWindow} persisted source activity`
            : "Configured source activity"}
        </p>
      </div>

      <div className="watchlist-source-stats" aria-label="Twitter source totals">
        <SourceStat icon={<AtSign aria-hidden />} label="sources" value={rows.length} />
        <SourceStat icon={<Bell aria-hidden />} label="unread" value={totals.unread} />
        <SourceStat icon={<SignalHigh aria-hidden />} label="signals" value={totals.signals} />
      </div>

      <nav
        aria-busy={updating ? "true" : undefined}
        aria-label="Twitter source list"
        className="watchlist-source-list"
      >
        {rows.map((row) => (
          <Link
            aria-current={row.handle === selectedHandle ? "page" : undefined}
            className="watchlist-source-row"
            data-active={row.handle === selectedHandle ? "true" : undefined}
            key={row.handle}
            to={watchlistSourceHref(row.handle, timelineScope)}
          >
            <span className="watchlist-source-row-main">
              <b>@{row.handle}</b>
              <small>{lastSeenLabel(row.lastSeenAtMs)}</small>
            </span>
            <span className="watchlist-source-row-counts" aria-label={`${row.handle} stats`}>
              <span>{row.recentSignalCount} signals</span>
              <span>{row.recentSourceCount} posts</span>
              {row.unreadCount > 0 ? <strong>{row.unreadCount} unread</strong> : null}
              {row.summaryIsStale ? <em>stale</em> : null}
            </span>
            <span className="watchlist-source-meter" aria-hidden>
              <span style={{ width: `${Math.max(6, (row.activityScore / maxActivity) * 100)}%` }} />
            </span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}

function SourceStat({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <span className="watchlist-source-stat">
      {icon}
      <b>{value}</b>
      <small>{label}</small>
    </span>
  );
}

function lastSeenLabel(value: number | null): string {
  return value ? `${formatRelativeTime(value)} ago` : "no recent posts";
}

function sourceTotals(rows: WatchlistRow[]): { signals: number; unread: number } {
  return rows.reduce(
    (totals, row) => ({
      signals: totals.signals + row.recentSignalCount,
      unread: totals.unread + row.unreadCount,
    }),
    { signals: 0, unread: 0 },
  );
}

function watchlistSourceHref(handle: string, timelineScope: WatchlistTimelineScope): string {
  const params = new URLSearchParams({ handle, timeline_scope: timelineScope });
  return `/watchlist?${params.toString()}`;
}
