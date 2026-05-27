import type { AppSession } from "@app/useAppSession";
import {
  useCockpitStatusQuery,
  type CockpitShellProps,
  type SearchShellProps,
} from "@features/cockpit";
import {
  useLiveRouteState,
  useLiveSelection,
  type LiveMobileTask,
  type LiveSignalTapeItem,
} from "@features/live/shell";
import { useNotificationsController } from "@features/notifications";
import type { LivePayload, ScopeKey, SignalPulseItem, TokenFlowItem, WindowKey } from "@lib/types";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import { useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { useLocation } from "react-router-dom";

export type ShellRouteContext = {
  configuredWatchlistHandles: string[];
  liveRouteHandles: string;
  mobileTask: LiveMobileTask;
  onMarkHandleRead: (handle: string) => void;
  scope: ScopeKey;
  selectedAccountEventId: string | null;
  selectedPulseItemId: string | null;
  selectedTapeEventId: string | null;
  selectAccountEvent: (item: LivePayload) => void;
  selectPulseItem: (item: SignalPulseItem) => void;
  selectToken: (item: TokenFlowItem) => void;
  socketStatus: string;
  token: string;
  updateScope: (scope: ScopeKey) => void;
  updateWindow: (window: WindowKey) => void;
  windowKey: WindowKey;
  onMobileTaskChange: (task: LiveMobileTask) => void;
  onTapeSelect: (item: LiveSignalTapeItem) => void;
};

export type ShellChromeData = {
  cockpitShellProps: CockpitShellProps;
  routeContext: ShellRouteContext;
  searchShellProps: SearchShellProps;
};

export function useShellChromeData(session: AppSession): ShellChromeData {
  const location = useLocation();
  const queryClient = useQueryClient();
  const liveRoute = useLiveRouteState();
  const statusQuery = useCockpitStatusQuery({ token: session.token });
  const socketSnapshot = useSocketSnapshot();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const bootstrapHandles = session.bootstrapHandles;
  const scope = liveRoute.scope;
  const status = statusQuery.data?.data ?? null;
  const token = session.token;
  const windowKey = liveRoute.window;
  const selection = useLiveSelection({ scope });
  const notificationsController = useNotificationsController({
    enabled: true,
    fallbackSummary: null,
    setMobileTask: selection.setMobileTask,
    socketNotifications: socketSnapshot.notificationItems,
    token,
  });
  const configuredWatchlistHandles = bootstrapHandles;
  const routeContext: ShellRouteContext = {
    configuredWatchlistHandles,
    liveRouteHandles: liveRoute.handles,
    mobileTask: selection.mobileTask,
    onMarkHandleRead: notificationsController.markAuthorRead,
    onMobileTaskChange: selection.handleMobileTaskChange,
    onTapeSelect: selection.handleTapeSelect,
    scope,
    selectAccountEvent: selection.selectAccountEvent,
    selectPulseItem: selection.selectPulseItem,
    selectToken: selection.selectToken,
    selectedAccountEventId: selection.selectedAccountEventId,
    selectedPulseItemId: selection.selectedPulseItemId,
    selectedTapeEventId: selection.selectedTapeEventId,
    socketStatus: socketSnapshot.status,
    token,
    updateScope: liveRoute.updateScope,
    updateWindow: liveRoute.updateWindow,
    windowKey,
  };
  const handleHotkey = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement;
    const isTyping = target.tagName === "INPUT" || target.tagName === "TEXTAREA";
    if (event.key === "/" && !isTyping) {
      event.preventDefault();
      searchInputRef.current?.focus();
      return;
    }
    if (isTyping) {
      return;
    }
    if (!shouldHandleLiveWindowHotkey(location.pathname, event.key)) {
      return;
    }
    if (event.key === "1") liveRoute.updateWindow("5m");
    if (event.key === "2") liveRoute.updateWindow("1h");
    if (event.key === "3") liveRoute.updateWindow("4h");
    if (event.key === "4") liveRoute.updateWindow("24h");
  };
  const topbarProps = {
    search: {
      inputRef: searchInputRef,
      onSubmitQuery: selection.submitEvidenceSearch,
    },
    status: {
      socketStatus: socketSnapshot.status,
      lastSocketMessageAt: socketSnapshot.lastMessageAt,
      status,
      statusLoading: Boolean(token) && statusQuery.isPending,
      statusError: statusQuery.isError,
      configReady: Boolean(token),
    },
    notifications: {
      summary: notificationsController.notificationSummary,
      drawerOpen: notificationsController.drawerOpen,
      onToggleDrawer: notificationsController.toggleDrawer,
    },
    onRefresh: () => void queryClient.invalidateQueries(),
  };
  const notificationProps = {
    notifications: notificationsController.notifications,
    notificationSummary: notificationsController.notificationSummary,
    notificationDrawerOpen: notificationsController.drawerOpen,
    notificationsLoading: notificationsController.notificationsLoading,
    onCloseNotificationDrawer: notificationsController.closeDrawer,
    onMarkAllRead: notificationsController.markAllRead,
    onMarkRead: notificationsController.markRead,
    onOpenNotification: notificationsController.openNotification,
    socketNotifications: socketSnapshot.notificationItems,
  };
  const shellProps = {
    notifications: notificationProps,
    topbar: topbarProps,
    onHotkey: handleHotkey,
    outletContext: routeContext,
  };

  return {
    cockpitShellProps: shellProps,
    routeContext,
    searchShellProps: {
      ...shellProps,
      topbar: {
        ...shellProps.topbar,
        search: { ...shellProps.topbar.search, showMainRouteButton: true },
      },
    },
  };
}

export function shouldHandleLiveWindowHotkey(pathname: string, key: string): boolean {
  if (!["1", "2", "3", "4"].includes(key)) {
    return false;
  }
  const path = pathname.split("?")[0] ?? pathname;
  return path === "/" || path.startsWith("/stocks");
}
