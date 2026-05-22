import { NotificationDrawer, NotificationToastBridge } from "@features/notifications";
import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "@lib/types";
import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { CockpitSideRail, type CockpitSideRailProps } from "./CockpitSideRail";
import { CockpitTopbar, type CockpitTopbarProps } from "./CockpitTopbar";
import { MobileRouteNav } from "./MobileRouteNav";
import "./cockpitShell.css";
import "./cockpitShellContract.css";

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
  onHotkey: (event: KeyboardEvent) => void;
};

export function CockpitShell({ topbar, sideRail, notifications, onHotkey }: CockpitShellProps) {
  useShellHotkeys(onHotkey);

  return (
    <div className="cockpit-shell">
      <CockpitTopbar {...topbar} />
      <MobileRouteNav />
      <div className="cockpit-grid">
        <CockpitSideRail {...sideRail} />
        <section className="center-column">
          <Outlet />
        </section>
      </div>
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
