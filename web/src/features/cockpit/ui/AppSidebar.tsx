import * as Collapsible from "@radix-ui/react-collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from "@shared/ui/sidebar";
import { ChevronRight } from "lucide-react";
import { useEffect, useId, useState } from "react";
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
  const [open, setOpen] = useBranchOpen(active);
  const contentId = useId();

  if (item.children?.length) {
    return (
      <Collapsible.Root asChild open={open} onOpenChange={setOpen}>
        <SidebarMenuItem data-state={open ? "open" : "closed"}>
          <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
            <Link onClick={closeSidebarOnNavigate} to={item.to}>
              {Icon ? <Icon aria-hidden /> : null}
              <span>{item.label}</span>
            </Link>
          </SidebarMenuButton>
          <BranchToggle contentId={contentId} label={item.label} open={open} />
          <Collapsible.Content asChild id={contentId}>
            <SidebarMenuSub className="cockpit-app-sidebar-menu-sub" data-depth={1}>
              {item.children.map((child) => (
                <AppSidebarSubItem depth={1} item={child} key={child.to} />
              ))}
            </SidebarMenuSub>
          </Collapsible.Content>
        </SidebarMenuItem>
      </Collapsible.Root>
    );
  }

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
        <NavLink end={item.end} onClick={closeSidebarOnNavigate} to={item.to}>
          {Icon ? <Icon aria-hidden /> : null}
          <span>{item.label}</span>
        </NavLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

function AppSidebarSubItem({ depth, item }: { depth: number; item: AppNavigationItem }) {
  const active = useAppNavigationMatch(item);
  const closeSidebarOnNavigate = useCloseSidebarOnNavigate();
  const [open, setOpen] = useBranchOpen(active);
  const contentId = useId();

  if (item.children?.length) {
    return (
      <Collapsible.Root asChild open={open} onOpenChange={setOpen}>
        <SidebarMenuSubItem data-state={open ? "open" : "closed"}>
          <SidebarMenuSubButton
            asChild
            className="cockpit-app-sidebar-menu-sub-button"
            data-depth={depth}
            isActive={active}
          >
            <NavLink end onClick={closeSidebarOnNavigate} to={item.to}>
              <span>{item.label}</span>
            </NavLink>
          </SidebarMenuSubButton>
          <BranchToggle contentId={contentId} label={item.label} open={open} />
          <Collapsible.Content asChild id={contentId}>
            <SidebarMenuSub className="cockpit-app-sidebar-menu-sub" data-depth={depth + 1}>
              {item.children.map((child) => (
                <AppSidebarSubItem depth={depth + 1} item={child} key={child.to} />
              ))}
            </SidebarMenuSub>
          </Collapsible.Content>
        </SidebarMenuSubItem>
      </Collapsible.Root>
    );
  }

  return (
    <SidebarMenuSubItem>
      <SidebarMenuSubButton
        asChild
        className="cockpit-app-sidebar-menu-sub-button"
        data-depth={depth}
        isActive={active}
      >
        <NavLink end={item.end} onClick={closeSidebarOnNavigate} to={item.to}>
          <span>{item.label}</span>
        </NavLink>
      </SidebarMenuSubButton>
    </SidebarMenuSubItem>
  );
}

function BranchToggle({
  contentId,
  label,
  open,
}: {
  contentId: string;
  label: string;
  open: boolean;
}) {
  return (
    <Collapsible.Trigger asChild>
      <SidebarMenuAction
        aria-controls={contentId}
        aria-expanded={open}
        aria-label={`${open ? "收起" : "展开"}${label}`}
        className="cockpit-app-sidebar-branch-toggle"
        type="button"
      >
        <ChevronRight aria-hidden />
      </SidebarMenuAction>
    </Collapsible.Trigger>
  );
}

function useBranchOpen(active: boolean): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(active);

  useEffect(() => {
    if (active) {
      setOpen(true);
    }
  }, [active]);

  return [open, setOpen];
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
