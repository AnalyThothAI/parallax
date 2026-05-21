import { useEffect } from "react";
import { Outlet } from "react-router-dom";

import { NotificationLayer, type ShellNotificationProps } from "./CockpitShell";
import { CockpitTopbar, type CockpitTopbarProps } from "./CockpitTopbar";
import { MobileRouteNav } from "./MobileRouteNav";

export type SearchShellProps = {
  topbar: CockpitTopbarProps;
  notifications: ShellNotificationProps;
  onHotkey: (event: KeyboardEvent) => void;
};

export function SearchShell({ topbar, notifications, onHotkey }: SearchShellProps) {
  useEffect(() => {
    document.addEventListener("keydown", onHotkey);
    return () => document.removeEventListener("keydown", onHotkey);
  }, [onHotkey]);

  return (
    <div className="cockpit-shell search-shell">
      <CockpitTopbar {...topbar} search={{ ...topbar.search, showMainRouteButton: true }} />
      <MobileRouteNav />
      <div className="cockpit-grid search-focus-mode">
        <section className="center-column">
          <Outlet />
        </section>
      </div>
      <NotificationLayer {...notifications} />
    </div>
  );
}
