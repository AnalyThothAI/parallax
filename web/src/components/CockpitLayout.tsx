import { Clock3, RefreshCw, Search, UserRound, Wifi, Zap } from "lucide-react";
import type { KeyboardEvent, ReactNode, RefObject } from "react";
import { Link, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import type {
  Decision,
  NotificationItem,
  NotificationLivePayload,
  NotificationSummary,
  ScopeKey,
  StatusData,
  WindowKey,
} from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";
import type { WatchlistRow } from "../lib/watchlist";

import { MobileTaskNav, type MobileTask } from "./MobileTaskNav";
import { NotificationBell } from "./NotificationBell";
import { NotificationDrawer } from "./NotificationDrawer";
import { NotificationToastBridge } from "./NotificationToastBridge";
import { RadarControls } from "./RadarControls";
import { WatchlistNotificationDot } from "./WatchlistNotificationDot";

type DecisionCounts = Record<Decision, number>;

type CockpitLayoutProps = {
  // search
  searchInputRef: RefObject<HTMLInputElement | null>;
  searchValue: string;
  onSearchChange: (value: string) => void;
  onSubmitSearch: () => void;
  // status
  socketStatus: string;
  lastSocketMessageAt: number | null;
  status?: StatusData | null;
  statusLoading: boolean;
  statusError: boolean;
  configReady: boolean;
  // top stats
  liveItemsCount: number;
  tokenItemsCount: number;
  windowKey: WindowKey;
  signalLabSummaryTrade: number;
  signalLabSummaryToken: number;
  signalLabSummaryTheme: number;
  signalLabPulseTotal: number;
  // notifications
  notifications: NotificationItem[];
  notificationSummary: NotificationSummary | null;
  notificationDrawerOpen: boolean;
  onToggleNotificationDrawer: () => void;
  onCloseNotificationDrawer: () => void;
  notificationsLoading: boolean;
  onMarkAllRead: () => void;
  onMarkRead: (notificationId: string) => void;
  onOpenNotification: (notification: NotificationItem) => void;
  socketNotifications: NotificationLivePayload[];
  // refresh
  onRefresh: () => void;
  // sidebar / scope
  scope: ScopeKey;
  onScopeChange: (scope: ScopeKey) => void;
  handles: string;
  onHandlesChange: (handles: string) => void;
  onWindowChange: (window: WindowKey) => void;
  decisionCounts: DecisionCounts;
  watchlistRows: WatchlistRow[];
  // mobile
  mobileTask: MobileTask;
  detailAvailable: boolean;
  onMobileTaskChange: (task: MobileTask) => void;
  // detail panel content
  detailPanel: ReactNode;
  // hotkeys
  onHotkey: (event: KeyboardEvent<HTMLElement>) => void;
};

const SIGNAL_LAB_PATH = "/signal-lab";

export function CockpitLayout(props: CockpitLayoutProps) {
  const {
    searchInputRef,
    searchValue,
    onSearchChange,
    onSubmitSearch,
    socketStatus,
    lastSocketMessageAt,
    status,
    statusLoading,
    statusError,
    configReady,
    liveItemsCount,
    tokenItemsCount,
    windowKey,
    signalLabSummaryTrade,
    signalLabSummaryToken,
    signalLabSummaryTheme,
    signalLabPulseTotal,
    notifications,
    notificationSummary,
    notificationDrawerOpen,
    onToggleNotificationDrawer,
    onCloseNotificationDrawer,
    notificationsLoading,
    onMarkAllRead,
    onMarkRead,
    onOpenNotification,
    socketNotifications,
    onRefresh,
    scope,
    onScopeChange,
    handles,
    onHandlesChange,
    onWindowChange,
    decisionCounts,
    watchlistRows,
    mobileTask,
    detailAvailable,
    onMobileTaskChange,
    detailPanel,
    onHotkey,
  } = props;

  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isSignalLab = location.pathname.startsWith(SIGNAL_LAB_PATH);
  const isSearch = location.pathname.startsWith("/search");
  const isLive = location.pathname === "/";
  const activeWatchHandle = isSignalLab ? (searchParams.get("handle") ?? "") : "";

  return (
    <main className="cockpit-shell" onKeyDown={onHotkey} tabIndex={-1}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden />
          <div className="brand-copy">
            <h1>intel.cockpit</h1>
            <p>/ws · localhost:8765</p>
          </div>
        </div>

        <StatusPills
          configReady={configReady}
          lastMessageAt={lastSocketMessageAt}
          socketStatus={socketStatus}
          status={status ?? undefined}
          statusError={statusError}
          statusLoading={statusLoading}
        />

        <form
          className="searchbar"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmitSearch();
          }}
        >
          <Search aria-hidden />
          <input
            ref={searchInputRef}
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索 CA / $TOKEN / @handle / 文本"
          />
          <button type="submit">检索</button>
        </form>

        <div className="top-stats">
          <span>
            MATCHED <b>{compactNumber(status?.collector.matched_twitter_events)}</b>
          </span>
          <span>
            flow·{windowKey} <b>{compactNumber(tokenItemsCount)}</b>
          </span>
          <span>
            trade <b>{compactNumber(signalLabSummaryTrade)}</b>
          </span>
          <span>
            token <b>{compactNumber(signalLabSummaryToken)}</b>
          </span>
          <span>
            theme <b>{compactNumber(signalLabSummaryTheme)}</b>
          </span>
        </div>

        <NotificationBell
          open={notificationDrawerOpen}
          summary={notificationSummary}
          onClick={onToggleNotificationDrawer}
        />

        <button
          className="icon-button"
          type="button"
          onClick={onRefresh}
          title="刷新"
          aria-label="刷新"
        >
          <RefreshCw aria-hidden />
        </button>
      </header>

      <div
        className={`cockpit-grid mobile-task-${mobileTask} ${isSignalLab ? "signal-lab-mode" : ""} ${isSearch ? "search-focus-mode" : ""}`}
      >
        <aside className="side-rail desktop-side-rail">
          <RailSection label="views">
            <RailButton
              active={isLive}
              label="Live"
              value={liveItemsCount}
              index="1"
              onClick={() => navigate("/")}
            />
            <RailButton
              active={isSignalLab}
              label="Signal Lab"
              value={signalLabPulseTotal}
              index="2"
              onClick={() => {
                navigate(SIGNAL_LAB_PATH);
                onMobileTaskChange("lab");
              }}
            />
          </RailSection>

          <RailSection label="scope">
            <div className="scope-stack">
              <button
                className={scope === "matched" ? "active" : ""}
                onClick={() => onScopeChange("matched")}
                type="button"
              >
                watched
              </button>
              <button
                className={scope === "all" ? "active" : ""}
                onClick={() => onScopeChange("all")}
                type="button"
              >
                all stream
              </button>
            </div>
            <label className="handle-filter">
              <UserRound aria-hidden />
              <input
                value={handles}
                onChange={(event) => onHandlesChange(event.target.value)}
                placeholder="toly, ansem"
              />
            </label>
          </RailSection>

          <RailSection label="decisions">
            <DecisionCount decision="driver" count={decisionCounts.driver} />
            <DecisionCount decision="watch" count={decisionCounts.watch} />
            <DecisionCount decision="investigate" count={decisionCounts.investigate} />
            <DecisionCount decision="discard" count={decisionCounts.discard} />
          </RailSection>

          <RailSection label="watchlist" className="watchlist-section">
            <div className="watchlist">
              {watchlistRows.map((row) => (
                <Link
                  className={`watchlist-row ${isSignalLab && activeWatchHandle === row.handle ? "active" : ""}`.trim()}
                  key={row.handle}
                  to={`/signal-lab?handle=${encodeURIComponent(row.handle)}`}
                >
                  <span className="watchlist-avatar">{row.handle.slice(0, 1).toUpperCase()}</span>
                  <span className="watchlist-copy">
                    <b>@{row.handle}</b>
                    <small>
                      {row.lastSeenAtMs
                        ? `${formatRelativeTime(row.lastSeenAtMs)} ago`
                        : "no recent"}
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

        <section className="responsive-control-panel" aria-label="cockpit controls">
          <RadarControls
            handles={handles}
            handlePlaceholder="handles"
            scope={scope}
            windowKey={windowKey}
            onHandlesChange={onHandlesChange}
            onScopeChange={onScopeChange}
            onWindowChange={onWindowChange}
          />
        </section>

        <section className="center-column">
          <Outlet />
        </section>

        <section className="detail-task-panel" data-mobile-task-panel="detail">
          {detailPanel}
        </section>
      </div>

      <MobileTaskNav
        activeTask={mobileTask}
        detailAvailable={detailAvailable}
        onTaskChange={onMobileTaskChange}
      />
      <NotificationDrawer
        loading={notificationsLoading}
        notifications={notifications}
        open={notificationDrawerOpen}
        summary={notificationSummary}
        onClose={onCloseNotificationDrawer}
        onMarkAllRead={onMarkAllRead}
        onMarkRead={onMarkRead}
        onOpenNotification={onOpenNotification}
      />
      <NotificationToastBridge
        notifications={socketNotifications.map((item) => item.notification)}
        onOpenNotification={onOpenNotification}
      />
    </main>
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
    <section className={`rail-section ${className}`.trim()}>
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
  value: number;
  index: string;
  onClick: () => void;
}) {
  return (
    <button className={`rail-button ${active ? "active" : ""}`} type="button" onClick={onClick}>
      <span>{index}</span>
      <b>{label}</b>
      <em>{compactNumber(value)}</em>
    </button>
  );
}

function DecisionCount({ decision, count }: { decision: Decision; count: number }) {
  return (
    <span className={`decision-count ${decision}`}>
      <span className={`decision-tag ${decision}`}>{decision}</span>
      <b>{compactNumber(count)}</b>
    </span>
  );
}

function StatusPills({
  socketStatus,
  configReady,
  status,
  statusLoading,
  statusError,
  lastMessageAt,
}: {
  socketStatus: string;
  configReady: boolean;
  status?: StatusData;
  statusLoading: boolean;
  statusError: boolean;
  lastMessageAt: number | null;
}) {
  const readiness = readinessLabel({ configReady, status, statusLoading, statusError });
  return (
    <div className="status-pills">
      <span className={configReady ? "pill good" : "pill warn"}>
        <Zap aria-hidden />
        {configReady ? "token ready" : "token"}
      </span>
      <span className={socketStatus === "connected" ? "pill good" : "pill warn"}>
        <Wifi aria-hidden />
        {socketStatus}
      </span>
      <span className={readiness.ok ? "pill good" : "pill warn"} title={readiness.title}>
        <Zap aria-hidden />
        {readiness.label}
      </span>
      <span className="pill muted">
        <Clock3 aria-hidden />
        {lastMessageAt ? `${formatRelativeTime(lastMessageAt)} ago` : "no msg"}
      </span>
    </div>
  );
}

function readinessLabel({
  configReady,
  status,
  statusLoading,
  statusError,
}: {
  configReady: boolean;
  status?: StatusData;
  statusLoading: boolean;
  statusError: boolean;
}): { label: string; ok: boolean; title?: string } {
  if (!configReady) {
    return { label: "status idle", ok: false };
  }
  if (statusLoading && !status) {
    return { label: "checking", ok: false };
  }
  if (statusError) {
    return { label: "status error", ok: false };
  }
  if (status?.ok) {
    return { label: "ready", ok: true };
  }
  return {
    label: "not ready",
    ok: false,
    title: status?.reasons?.join(", ") || undefined,
  };
}
