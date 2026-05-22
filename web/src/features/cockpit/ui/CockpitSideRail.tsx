import { WatchlistNotificationDot } from "@features/notifications";
import type { WatchlistRow } from "@features/watchlist";
import { compactNumber, formatRelativeTime } from "@lib/format";
import type { Decision, ScopeKey, WindowKey } from "@lib/types";
import { macroPath, newsPath, stocksPath, watchlistPath } from "@shared/routing/paths";
import { DecisionTag } from "@shared/ui/DecisionTag";
import { HandleFilter } from "@shared/ui/HandleFilter";
import clsx from "clsx";
import type { ReactNode } from "react";
import { Link, useMatch, useNavigate, useSearchParams } from "react-router-dom";

import "./CockpitSideRail.css";

type DecisionCounts = Record<Decision, number>;

export type CockpitSideRailProps = {
  tokenItemsCount: number;
  stockItemsCount: number;
  newsItemsCount: number;
  newsItemsHasMore: boolean;
  scope: ScopeKey;
  onScopeChange: (scope: ScopeKey) => void;
  handles: string;
  onHandlesChange: (handles: string) => void;
  onWindowChange: (window: WindowKey) => void;
  decisionCounts: DecisionCounts;
  watchlistRows: WatchlistRow[];
};

export function CockpitSideRail({
  tokenItemsCount,
  stockItemsCount,
  newsItemsCount,
  newsItemsHasMore,
  scope,
  onScopeChange,
  handles,
  onHandlesChange,
  onWindowChange: _onWindowChange,
  decisionCounts,
  watchlistRows,
}: CockpitSideRailProps) {
  const navigate = useNavigate();
  const liveRouteMatch = useMatch({ path: "/", end: true });
  const newsRouteMatch = useMatch("/news/*");
  const stockRouteMatch = useMatch("/stocks/*");
  const macroRouteMatch = useMatch("/macro/*");
  const watchlistRouteMatch = useMatch("/watchlist/*");
  const [searchParams] = useSearchParams();
  const activeWatchHandle = watchlistRouteMatch ? (searchParams.get("handle") ?? "") : "";

  return (
    <aside className="side-rail desktop-side-rail">
      <RailSection label="markets">
        <RailButton
          active={Boolean(liveRouteMatch)}
          index="1"
          label="Radar"
          value={tokenItemsCount}
          onClick={() => navigate("/")}
        />
        <RailButton
          active={Boolean(stockRouteMatch)}
          index="2"
          label="Stocks"
          value={stockItemsCount}
          onClick={() => navigate(stocksPath())}
        />
        <RailButton
          active={Boolean(newsRouteMatch)}
          index="3"
          label="News"
          value={newsItemsHasMore ? `${compactNumber(newsItemsCount)}+` : newsItemsCount}
          onClick={() => navigate(newsPath())}
        />
        <RailButton
          active={Boolean(macroRouteMatch)}
          index="M"
          label="Macro"
          onClick={() => navigate(macroPath())}
        />
      </RailSection>

      <RailSection label="scope">
        <div className="scope-stack">
          <button
            className={scope === "matched" ? "active" : ""}
            type="button"
            onClick={() => onScopeChange("matched")}
          >
            watched
          </button>
          <button
            className={scope === "all" ? "active" : ""}
            type="button"
            onClick={() => onScopeChange("all")}
          >
            all stream
          </button>
        </div>
        <HandleFilter
          ariaLabel="watchlist handles"
          id="cockpit-handle-filter"
          placeholder="toly, ansem"
          value={handles}
          onChange={onHandlesChange}
        />
      </RailSection>

      <RailSection label="decisions">
        <DecisionCount count={decisionCounts.driver} decision="driver" />
        <DecisionCount count={decisionCounts.watch} decision="watch" />
        <DecisionCount count={decisionCounts.investigate} decision="investigate" />
        <DecisionCount count={decisionCounts.discard} decision="discard" />
      </RailSection>

      <RailSection className="watchlist-section" label="watchlist">
        <div className="watchlist">
          {watchlistRows.map((row) => (
            <Link
              className={clsx("watchlist-row", activeWatchHandle === row.handle && "active")}
              key={row.handle}
              to={watchlistPath({ handle: row.handle })}
            >
              <span className="watchlist-avatar">{row.handle.slice(0, 1).toUpperCase()}</span>
              <span className="watchlist-copy">
                <b>@{row.handle}</b>
                <small>
                  {row.lastSeenAtMs ? `${formatRelativeTime(row.lastSeenAtMs)} ago` : "no recent"}
                </small>
              </span>
              <WatchlistNotificationDot count={row.unreadCount} />
            </Link>
          ))}
        </div>
      </RailSection>

      <div className="rail-footer">
        <span>kbd · 1-4 radar · / search</span>
      </div>
    </aside>
  );
}

function RailSection({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={clsx("rail-section", className)}>
      <h2>{label}</h2>
      {children}
    </section>
  );
}

function RailButton({
  active,
  label,
  value,
  index,
  onClick,
}: {
  active?: boolean;
  label: string;
  value?: number | string;
  index: string;
  onClick: () => void;
}) {
  return (
    <button className={clsx("rail-button", active && "active")} type="button" onClick={onClick}>
      <span>{index}</span>
      <b>{label}</b>
      {value !== undefined ? (
        <em>{typeof value === "number" ? compactNumber(value) : value}</em>
      ) : (
        <em />
      )}
    </button>
  );
}

function DecisionCount({ decision, count }: { decision: Decision; count: number }) {
  return (
    <span className={clsx("decision-count", decision)}>
      <DecisionTag decision={decision} />
      <b>{compactNumber(count)}</b>
    </span>
  );
}
