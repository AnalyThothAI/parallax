import { SidebarInset, SidebarProvider, SidebarTrigger } from "@shared/ui/sidebar";
import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { AppSidebar, type AppSidebarBadges } from "./AppSidebar";
import { NotificationLayer, type ShellNotificationProps } from "./CockpitShell";
import { CockpitTopbar, type CockpitTopbarProps } from "./CockpitTopbar";

export type SearchShellProps = {
  topbar: CockpitTopbarProps;
  sidebar: { badges: AppSidebarBadges };
  notifications: ShellNotificationProps;
  onHotkey: (event: KeyboardEvent) => void;
};

export function SearchShell({ topbar, sidebar, notifications, onHotkey }: SearchShellProps) {
  useEffect(() => {
    document.addEventListener("keydown", onHotkey);
    return () => document.removeEventListener("keydown", onHotkey);
  }, [onHotkey]);

  return (
    <SidebarProvider className="cockpit-shell search-shell">
      <AppSidebar badges={sidebar.badges} />
      <SidebarInset className="cockpit-main search-focus-mode">
        <CockpitTopbar
          {...topbar}
          navigationTrigger={<SidebarTrigger className="topbar-sidebar-trigger" />}
          search={{ ...topbar.search, showMainRouteButton: true }}
        />
        <section className="center-column">
          <Outlet />
        </section>
      </SidebarInset>
      <NotificationLayer {...notifications} />
    </SidebarProvider>
  );
}
