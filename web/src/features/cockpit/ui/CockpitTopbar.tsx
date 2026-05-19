import { NotificationBell } from "@features/notifications";
import { compactNumber, formatRelativeTime } from "@lib/format";
import type { NotificationSummary, StatusData, WindowKey } from "@lib/types";
import { opsPath } from "@shared/routing/paths";
import { IconButton } from "@shared/ui/IconButton";
import clsx from "clsx";
import { Clock3, Home, RefreshCw, Search, ServerCog, Wifi, Zap } from "lucide-react";
import { useState, type RefObject } from "react";
import { useMatch, useNavigate } from "react-router-dom";

export type CockpitTopbarProps = {
  search: {
    inputRef: RefObject<HTMLInputElement | null>;
    onSubmitQuery: (query: string) => void;
    showMainRouteButton?: boolean;
  };
  status: {
    socketStatus: string;
    lastSocketMessageAt: number | null;
    status?: StatusData | null;
    statusLoading: boolean;
    statusError: boolean;
    configReady: boolean;
  };
  stats: {
    tokenItemsCount: number;
    windowKey: WindowKey;
    signalLabSummaryTrade: number;
    signalLabSummaryToken: number;
    signalLabSummaryRisk: number;
  };
  notifications: {
    summary: NotificationSummary | null;
    drawerOpen: boolean;
    onToggleDrawer: () => void;
  };
  onRefresh: () => void;
};

export function CockpitTopbar({
  search,
  status,
  stats,
  notifications,
  onRefresh,
}: CockpitTopbarProps) {
  const navigate = useNavigate();
  const opsRouteMatch = useMatch("/ops/*");
  const [searchDraft, setSearchDraft] = useState("");
  const matchedTwitterEvents = numberDetail(
    status.status?.workers.collector?.details?.matched_twitter_events,
  );

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark" aria-hidden />
        <div className="brand-copy">
          <h1>gmgn.intel</h1>
          <p>obsidian desk</p>
        </div>
        <WsStatusBeacon
          lastMessageAt={status.lastSocketMessageAt}
          socketStatus={status.socketStatus}
        />
        {search.showMainRouteButton ? (
          <button className="main-route-button" type="button" onClick={() => navigate("/")}>
            <Home aria-hidden />
            Main
          </button>
        ) : null}
      </div>

      <StatusPills
        configReady={status.configReady}
        lastMessageAt={status.lastSocketMessageAt}
        socketStatus={status.socketStatus}
        status={status.status ?? undefined}
        statusError={status.statusError}
        statusLoading={status.statusLoading}
      />

      <form
        className="searchbar"
        onSubmit={(event) => {
          event.preventDefault();
          search.onSubmitQuery(searchDraft);
        }}
      >
        <Search aria-hidden />
        <label className="sr-only" htmlFor="global-search-input">
          Global search
        </label>
        <input
          aria-label="global search"
          id="global-search-input"
          placeholder="搜索 token / @handle / CA"
          ref={search.inputRef}
          value={searchDraft}
          onChange={(event) => setSearchDraft(event.target.value)}
        />
        <button type="submit">检索</button>
      </form>

      <div className="top-stats">
        <span>
          matched <b>{compactNumber(matchedTwitterEvents)}</b>
        </span>
        <span>
          flow·{stats.windowKey} <b>{compactNumber(stats.tokenItemsCount)}</b>
        </span>
        <span>
          trade <b>{compactNumber(stats.signalLabSummaryTrade)}</b>
        </span>
        <span>
          token <b>{compactNumber(stats.signalLabSummaryToken)}</b>
        </span>
        <span>
          risk <b>{compactNumber(stats.signalLabSummaryRisk)}</b>
        </span>
      </div>

      <button
        aria-current={opsRouteMatch ? "page" : undefined}
        aria-label="Open ops diagnostics"
        className={clsx("topbar-ops-button", opsRouteMatch && "active")}
        title="Open ops diagnostics"
        type="button"
        onClick={() => navigate(opsPath())}
      >
        <ServerCog aria-hidden />
      </button>

      <NotificationBell
        open={notifications.drawerOpen}
        summary={notifications.summary}
        onClick={notifications.onToggleDrawer}
      />

      <IconButton
        aria-label="刷新"
        className="topbar-refresh-button"
        title="刷新"
        onClick={onRefresh}
      >
        <RefreshCw aria-hidden />
      </IconButton>
    </header>
  );
}

function numberDetail(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function WsStatusBeacon({
  socketStatus,
  lastMessageAt,
}: {
  socketStatus: string;
  lastMessageAt: number | null;
}) {
  const state =
    socketStatus === "connected"
      ? "connected"
      : socketStatus === "connecting" || socketStatus === "authenticating"
        ? "connecting"
        : "offline";
  const label = [
    `WebSocket ${socketStatus}`,
    lastMessageAt ? `last message ${formatRelativeTime(lastMessageAt)} ago` : "no message yet",
  ].join(" · ");

  return (
    <span
      aria-label={label}
      className={clsx("ws-status-beacon", `state-${state}`)}
      role="status"
      title={label}
    >
      <Wifi aria-hidden />
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
    <div className="status-pills" aria-live="polite">
      <span className={clsx("pill", configReady ? "good" : "warn")}>
        <Zap aria-hidden />
        {configReady ? "token ready" : "token"}
      </span>
      <span className={clsx("pill", socketStatus === "connected" ? "good" : "warn")}>
        <Wifi aria-hidden />
        {socketStatus}
      </span>
      <span className={clsx("pill", readiness.ok ? "good" : "warn")} title={readiness.title}>
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
