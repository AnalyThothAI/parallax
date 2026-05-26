import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from "@shared/ui/sidebar";
import { Link, NavLink, useMatch } from "react-router-dom";

import { APP_NAVIGATION_GROUPS, type AppNavigationItem } from "./appNavigation";
import "./AppSidebar.css";

export function AppSidebar() {
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
                    <AppSidebarItem item={item} key={item.to} />
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

function AppSidebarItem({ item }: { item: AppNavigationItem }) {
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
      {item.children?.length ? (
        <SidebarMenuSub className="cockpit-app-sidebar-menu-sub" data-depth={1}>
          {item.children.map((child) => (
            <AppSidebarSubItem depth={1} item={child} key={child.to} />
          ))}
        </SidebarMenuSub>
      ) : null}
    </SidebarMenuItem>
  );
}

function AppSidebarSubItem({ depth, item }: { depth: number; item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton
        asChild
        className="cockpit-app-sidebar-menu-sub-button"
        data-depth={depth}
        isActive={active}
      >
        {item.children?.length ? (
          <NavLink end onClick={closeSidebarOnNavigate} to={item.to}>
            <span>{item.label}</span>
          </NavLink>
        ) : (
          <NavLink end={item.end} onClick={closeSidebarOnNavigate} to={item.to}>
            <span>{item.label}</span>
          </NavLink>
        )}
      </SidebarMenuSubButton>
      {item.children?.length ? (
        <SidebarMenuSub className="cockpit-app-sidebar-menu-sub" data-depth={depth + 1}>
          {item.children.map((child) => (
            <AppSidebarSubItem depth={depth + 1} item={child} key={child.to} />
          ))}
        </SidebarMenuSub>
      ) : null}
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
