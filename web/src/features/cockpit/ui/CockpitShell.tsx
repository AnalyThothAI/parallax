import { NotificationDrawer, NotificationToastBridge } from "@features/notifications";
import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "@lib/types";
import clsx from "clsx";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { Outlet, useMatch } from "react-router-dom";

import { CockpitMobileNav, type CockpitMobileNavProps } from "./CockpitMobileNav";
import { CockpitSideRail, type CockpitSideRailProps } from "./CockpitSideRail";
import { CockpitTopbar, type CockpitTopbarProps } from "./CockpitTopbar";
import { RadarControls } from "./RadarControls";

export type ShellNotificationProps = {
  notifications: NotificationItem[];
  notificationSummary: NotificationSummary | null;
  notificationDrawerOpen: boolean;
  notificationsLoading: boolean;
  onCloseNotificationDrawer: () => void;
  onMarkAllRead: () => void;
  onMarkRead: (notificationId: string) => void;
  onOpenNotification: (notification: NotificationItem) => void;
  socketNotifications: NotificationLivePayload[];
};

export type CockpitShellProps = {
  topbar: CockpitTopbarProps;
  sideRail: CockpitSideRailProps;
  notifications: ShellNotificationProps;
  mobile: CockpitMobileNavProps;
  detailPanel: ReactNode;
  onHotkey: (event: KeyboardEvent) => void;
};

export function CockpitShell({
  topbar,
  sideRail,
  notifications,
  mobile,
  detailPanel,
  onHotkey,
}: CockpitShellProps) {
  useShellHotkeys(onHotkey);
  const stockRouteMatch = useMatch("/stocks/*");
  const labRouteMatch = useMatch("/signal-lab/*");
  const routeModeClass = [
    stockRouteMatch ? "stocks-main-nav-mode" : "",
    labRouteMatch ? "signal-lab-mode" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={clsx("cockpit-shell", `mobile-task-${mobile.mobileTask}`)}>
      <CockpitTopbar {...topbar} />
      <div className={clsx("cockpit-grid", `mobile-task-${mobile.mobileTask}`, routeModeClass)}>
        <CockpitSideRail {...sideRail} />
        <section className="responsive-control-panel" aria-label="cockpit controls">
          <RadarControls
            handles={sideRail.handles}
            handlePlaceholder="handles"
            scope={sideRail.scope}
            windowKey={topbar.stats.windowKey}
            onHandlesChange={sideRail.onHandlesChange}
            onScopeChange={sideRail.onScopeChange}
            onWindowChange={sideRail.onWindowChange}
          />
        </section>
        <section className="center-column">
          <Outlet />
        </section>
        <section className="detail-task-panel" data-mobile-task-panel="detail">
          {detailPanel}
        </section>
      </div>
      <CockpitMobileNav {...mobile} detailAvailable={mobile.detailAvailable && !stockRouteMatch} />
      <NotificationLayer {...notifications} />
    </div>
  );
}

export function NotificationLayer({
  notifications,
  notificationSummary,
  notificationDrawerOpen,
  notificationsLoading,
  onCloseNotificationDrawer,
  onMarkAllRead,
  onMarkRead,
  onOpenNotification,
  socketNotifications,
}: ShellNotificationProps) {
  return (
    <>
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
    </>
  );
}

function useShellHotkeys(onHotkey: (event: KeyboardEvent) => void) {
  useEffect(() => {
    document.addEventListener("keydown", onHotkey);
    return () => document.removeEventListener("keydown", onHotkey);
  }, [onHotkey]);
}
