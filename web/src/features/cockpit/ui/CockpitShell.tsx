import { NotificationDrawer, NotificationToastBridge } from "@features/notifications";
import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "@lib/types";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@shared/ui/sidebar";
import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { AppSidebar, type AppSidebarBadges } from "./AppSidebar";
import { CockpitTopbar, type CockpitTopbarProps } from "./CockpitTopbar";
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
  sidebar: { badges: AppSidebarBadges };
  notifications: ShellNotificationProps;
  onHotkey: (event: KeyboardEvent) => void;
};

export function CockpitShell({ topbar, sidebar, notifications, onHotkey }: CockpitShellProps) {
  useShellHotkeys(onHotkey);

  return (
    <SidebarProvider className="cockpit-shell">
      <AppSidebar badges={sidebar.badges} />
      <SidebarInset className="cockpit-main">
        <CockpitTopbar
          {...topbar}
          navigationTrigger={<SidebarTrigger className="topbar-sidebar-trigger" />}
        />
        <section className="center-column">
          <Outlet />
        </section>
      </SidebarInset>
      <NotificationLayer {...notifications} />
    </SidebarProvider>
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
