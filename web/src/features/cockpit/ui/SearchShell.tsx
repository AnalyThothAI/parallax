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
  outletContext?: unknown;
};

export function SearchShell({
  topbar,
  sidebar,
  notifications,
  onHotkey,
  outletContext,
}: SearchShellProps) {
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
        />
        <section className="center-column">
          <Outlet context={outletContext} />
        </section>
      </SidebarInset>
      <NotificationLayer {...notifications} />
    </SidebarProvider>
  );
}
