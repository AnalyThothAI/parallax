import { compactNumber } from "@lib/format";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from "@shared/ui/sidebar";
import { Link, NavLink, useMatch } from "react-router-dom";

import {
  APP_NAVIGATION_GROUPS,
  type AppNavigationBadgeKey,
  type AppNavigationItem,
} from "./appNavigation";
import "./AppSidebar.css";

export type AppSidebarBadges = Partial<Record<AppNavigationBadgeKey, number | string>>;

export function AppSidebar({ badges = {} }: { badges?: AppSidebarBadges }) {
  return (
    <Sidebar
      className="cockpit-app-sidebar"
      collapsible="icon"
      variant="sidebar"
      aria-label="Application sidebar"
    >
      <SidebarHeader className="cockpit-app-sidebar-header">
        <div className="cockpit-app-sidebar-brand">
          <span className="cockpit-app-sidebar-mark" aria-hidden />
          <span>
            <b>gmgn.intel</b>
            <small>obsidian desk</small>
          </span>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label="Primary navigation" className="cockpit-app-sidebar-nav">
          {APP_NAVIGATION_GROUPS.map((group) => (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel asChild>
                <h2 className="cockpit-app-sidebar-group-heading">{group.label}</h2>
              </SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {group.items.map((item) => (
                    <AppSidebarItem badge={badgeForItem(item, badges)} item={item} key={item.to} />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          ))}
        </nav>
      </SidebarContent>
      <SidebarFooter className="cockpit-app-sidebar-footer">
        <div aria-label="Desk status" className="cockpit-app-sidebar-status" role="status">
          <span className="cockpit-app-sidebar-status-dot" aria-hidden />
          <span className="cockpit-app-sidebar-status-copy">
            <strong>Live desk</strong>
            <small>facts online</small>
          </span>
        </div>
      </SidebarFooter>
      <SidebarRail className="cockpit-app-sidebar-rail" />
    </Sidebar>
  );
}

function AppSidebarItem({ badge, item }: { badge?: string; item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();
  const Icon = item.icon;

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
        {item.children?.length ? (
          <Link onClick={closeSidebarOnNavigate} to={item.to}>
            {Icon ? <Icon aria-hidden /> : null}
            <span>{item.label}</span>
          </Link>
        ) : (
          <NavLink end={item.end} onClick={closeSidebarOnNavigate} to={item.to}>
            {Icon ? <Icon aria-hidden /> : null}
            <span>{item.label}</span>
          </NavLink>
        )}
      </SidebarMenuButton>
      {badge !== undefined ? <SidebarMenuBadge>{badge}</SidebarMenuBadge> : null}
      {item.children?.length ? (
        <SidebarMenuSub>
          {item.children.map((child) => (
            <AppSidebarSubItem item={child} key={child.to} />
          ))}
        </SidebarMenuSub>
      ) : null}
    </SidebarMenuItem>
  );
}

function AppSidebarSubItem({ item }: { item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton asChild isActive={active}>
        <NavLink end={item.end} onClick={closeSidebarOnNavigate} to={item.to}>
          <span>{item.label}</span>
        </NavLink>
      </SidebarMenuSubButton>
    </SidebarMenuSubItem>
  );
}

function useAppNavigationMatch(item: AppNavigationItem): boolean {
  const match = useMatch({
    end: item.end ?? false,
    path: item.matchPath ?? item.to,
  });
  return Boolean(match);
}

function useCloseSidebarOnNavigate() {
  const { isMobile, setOpenMobile } = useSidebar();

  return () => {
    if (isMobile) {
      setOpenMobile(false);
    }
  };
}

function badgeForItem(item: AppNavigationItem, badges: AppSidebarBadges): string | undefined {
  if (!item.badgeKey) {
    return undefined;
  }
  const value = badges[item.badgeKey];
  if (value === undefined) {
    return undefined;
  }
  return typeof value === "number" ? compactNumber(value) : value;
}
