import { WatchlistNotificationDot } from "@features/notifications";
import { compactNumber, formatRelativeTime } from "@lib/format";
import type { Decision, ScopeKey, WindowKey } from "@lib/types";
import type { WatchlistRow } from "@lib/watchlist";
import { signalLabPath, stocksPath } from "@shared/routing/paths";
import clsx from "clsx";
import { UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useMatch, useNavigate, useSearchParams } from "react-router-dom";

import type { MobileTask } from "../model/mobileTask";

type DecisionCounts = Record<Decision, number>;

export type CockpitSideRailProps = {
  tokenItemsCount: number;
  signalLabPulseTotal: number;
  scope: ScopeKey;
  onScopeChange: (scope: ScopeKey) => void;
  handles: string;
  onHandlesChange: (handles: string) => void;
  onWindowChange: (window: WindowKey) => void;
  decisionCounts: DecisionCounts;
  watchlistRows: WatchlistRow[];
  onMobileTaskChange: (task: MobileTask) => void;
};

export function CockpitSideRail({
  tokenItemsCount,
  signalLabPulseTotal,
  scope,
  onScopeChange,
  handles,
  onHandlesChange,
  onWindowChange: _onWindowChange,
  decisionCounts,
  watchlistRows,
  onMobileTaskChange,
}: CockpitSideRailProps) {
  const navigate = useNavigate();
  const liveRouteMatch = useMatch({ path: "/", end: true });
  const stockRouteMatch = useMatch("/stocks/*");
  const labRouteMatch = useMatch("/signal-lab/*");
  const [searchParams] = useSearchParams();
  const activeWatchHandle = labRouteMatch ? (searchParams.get("handle") ?? "") : "";

  return (
    <aside className="side-rail desktop-side-rail">
      <RailSection label="views">
        <RailButton
          active={Boolean(liveRouteMatch)}
          index="1"
          label="Token"
          value={tokenItemsCount}
          onClick={() => navigate("/")}
        />
        <RailButton
          active={Boolean(stockRouteMatch)}
          index="2"
          label="Stocks"
          onClick={() => navigate(stocksPath())}
        />
        <RailButton
          active={Boolean(labRouteMatch)}
          index="3"
          label="Signal Labs"
          value={signalLabPulseTotal}
          onClick={() => {
            navigate(signalLabPath());
            onMobileTaskChange("lab");
          }}
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
        <label className="handle-filter" htmlFor="cockpit-handle-filter">
          <UserRound aria-hidden />
          <input
            aria-label="watchlist handles"
            id="cockpit-handle-filter"
            placeholder="toly, ansem"
            value={handles}
            onChange={(event) => onHandlesChange(event.target.value)}
          />
        </label>
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
              to={signalLabPath({ handle: row.handle })}
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
  value?: number;
  index: string;
  onClick: () => void;
}) {
  return (
    <button className={clsx("rail-button", active && "active")} type="button" onClick={onClick}>
      <span>{index}</span>
      <b>{label}</b>
      {value !== undefined ? <em>{compactNumber(value)}</em> : <em />}
    </button>
  );
}

function DecisionCount({ decision, count }: { decision: Decision; count: number }) {
  return (
    <span className={clsx("decision-count", decision)}>
      <span className={clsx("decision-tag", decision)}>{decision}</span>
      <b>{compactNumber(count)}</b>
    </span>
  );
}
