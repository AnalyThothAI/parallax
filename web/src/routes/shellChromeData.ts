import type { AppSession } from "@app/useAppSession";
import { useCockpitStatusQuery, type CockpitShellProps, type SearchShellProps } from "@features/cockpit";
import {
  buildLiveSignalTapeItems,
  useLiveRadarRouteData,
  useLiveRecentQuery,
  useLiveRouteState,
  useLiveSelection,
  type LiveMobileTask,
  type LiveSignalTapeItem,
} from "@features/live/shell";
import { NEWS_PAGE_SIZE, useNewsPageWithToken } from "@features/news/shell";
import { useNotificationsController } from "@features/notifications";
import { useSignalLabCompactQuery } from "@features/signal-lab/shell";
import { useStocksRadarQuery } from "@features/stocks/shell";
import type {
  LivePayload,
  NotificationSummary,
  ScopeKey,
  SignalPulseData,
  SignalPulseItem,
  TokenFlowItem,
  WindowKey,
} from "@lib/types";
import { useSocketSnapshot } from "@shared/socket/socketContext";
import type { MarketTargetRef } from "@shared/socket/socketTypes";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { useLocation } from "react-router-dom";

const EMPTY_HANDLES: string[] = [];
const EMPTY_LIVE_ITEMS: LivePayload[] = [];
const EMPTY_NEWS_ROWS: unknown[] = [];

export type ShellRouteContext = {
  accountUnreadCounts: NotificationSummary["account_unread_counts"] | undefined;
  assetFlowError: Error | null;
  configuredWatchlistHandles: string[];
  hiddenSignalLabPulseData: SignalPulseData | null;
  hiddenSignalPulseLoading: boolean;
  isAssetFlowLoading: boolean;
  isAssetFlowRefreshing: boolean;
  isRecentLoading: boolean;
  liveSignalTapeItems: LiveSignalTapeItem[];
  marketTargets: MarketTargetRef[];
  mobileTask: LiveMobileTask;
  onMarkHandleRead: (handle: string) => void;
  scope: ScopeKey;
  selectedAccountEventId: string | null;
  selectedPulseItemId: string | null;
  selectedTapeEventId: string | null;
  selectAccountEvent: (item: LivePayload) => void;
  selectPulseItem: (item: SignalPulseItem) => void;
  selectToken: (item: TokenFlowItem) => void;
  signalLabOverviewData: SignalPulseData | undefined;
  signalLabPulseData: SignalPulseData | null;
  signalPulseLoading: boolean;
  socketStatus: string;
  token: string;
  tokenItems: TokenFlowItem[];
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
  const routeActivity = useMemo(
    () => shellRouteActivity(location.pathname),
    [location.pathname],
  );
  const statusQuery = useCockpitStatusQuery({ token: session.token });
  const recentQuery = useLiveRecentQuery({
    enabled: routeActivity.liveDeck,
    handles: liveRoute.handles,
    scope: liveRoute.scope,
    token: session.token,
  });
  const stocksRadarQuery = useStocksRadarQuery({
    enabled: routeActivity.stocksBadge,
    scope: liveRoute.scope,
    token: session.token,
    window: liveRoute.window,
  });
  const newsRowsQuery = useNewsPageWithToken(session.token, {
    enabled: routeActivity.newsBadge,
    limit: NEWS_PAGE_SIZE,
  });
  const liveRadar = useLiveRadarRouteData({
    enabled: routeActivity.liveRadar,
    scope: liveRoute.scope,
    token: session.token,
    window: liveRoute.window,
  });
  const signalLabCompact = useSignalLabCompactQuery({
    enabled: routeActivity.signalLabCompact,
    token: session.token,
  });
  const socketSnapshot = useSocketSnapshot();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const bootstrapHandles = session.bootstrapHandles;
  const recentReplayItems = recentQuery.data?.data.items ?? EMPTY_LIVE_ITEMS;
  const scope = liveRoute.scope;
  const status = statusQuery.data?.data ?? null;
  const statusHandles = statusQuery.data?.data.handles ?? EMPTY_HANDLES;
  const token = session.token;
  const tokenItems = liveRadar.tokenItems;
  const stockItemsCount =
    stocksRadarQuery.data?.health?.returned_count ?? stocksRadarQuery.data?.rows?.length ?? 0;
  const newsRows = newsRowsQuery.data?.items ?? EMPTY_NEWS_ROWS;
  const newsItemsHasMore = Boolean(newsRowsQuery.data?.next_cursor);
  const windowKey = liveRoute.window;
  const liveItems = useMemo(
    () => mergeLiveItems(recentReplayItems, socketSnapshot.eventItems),
    [recentReplayItems, socketSnapshot.eventItems],
  );
  const liveSignalTapeItems = useMemo(
    () => buildLiveSignalTapeItems({ liveItems, tokenItems }),
    [liveItems, tokenItems],
  );
  const selection = useLiveSelection({ scope });
  const notificationsController = useNotificationsController({
    enabled: routeActivity.notifications,
    fallbackSummary: null,
    prefetchList: routeActivity.notificationList,
    setMobileTask: selection.setMobileTask,
    socketNotifications: socketSnapshot.notificationItems,
    token,
  });
  const configuredWatchlistHandles = statusHandles.length ? statusHandles : bootstrapHandles;
  const routeContext: ShellRouteContext = {
    accountUnreadCounts: notificationsController.notificationSummary?.account_unread_counts,
    assetFlowError: liveRadar.assetFlowError,
    configuredWatchlistHandles,
    hiddenSignalLabPulseData: signalLabCompact.hiddenSignalPulseData,
    hiddenSignalPulseLoading: signalLabCompact.hiddenSignalPulseLoading,
    isAssetFlowLoading: liveRadar.isAssetFlowLoading,
    isAssetFlowRefreshing: liveRadar.isAssetFlowRefreshing,
    isRecentLoading: recentQuery.isPending,
    liveSignalTapeItems,
    marketTargets: liveRadar.marketTargets,
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
    signalLabOverviewData: signalLabCompact.overviewData,
    signalLabPulseData: signalLabCompact.pulseData ?? null,
    signalPulseLoading: signalLabCompact.signalPulseColdLoading,
    socketStatus: socketSnapshot.status,
    token,
    tokenItems,
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
    stats: {
      tokenItemsCount: tokenItems.length,
      windowKey,
      signalLabSummaryTrade: signalLabCompact.overviewData?.summary.trade_candidate ?? 0,
      signalLabSummaryToken: signalLabCompact.overviewData?.summary.token_watch ?? 0,
      signalLabSummaryRisk:
        signalLabCompact.overviewData?.summary.risk_rejected_high_info ?? 0,
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
  const sidebarProps = {
    badges: {
      news: newsItemsHasMore ? `${newsRows.length}+` : newsRows.length,
      stocks: stockItemsCount,
      token: tokenItems.length,
    },
  };
  const shellProps = {
    notifications: notificationProps,
    sidebar: sidebarProps,
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

function shellRouteActivity(pathname: string) {
  const isLiveRoute = pathname === "/";
  const isStocksRoute = pathname.startsWith("/stocks");
  const isNewsRoute = pathname.startsWith("/news");
  const isSignalLabRoute = pathname.startsWith("/signal-lab");

  return {
    liveDeck: isLiveRoute,
    liveRadar: isLiveRoute,
    newsBadge: isLiveRoute || isNewsRoute,
    notificationList: isLiveRoute,
    notifications: true,
    signalLabCompact: isLiveRoute || isSignalLabRoute,
    stocksBadge: isLiveRoute || isStocksRoute,
  };
}

export function shouldHandleLiveWindowHotkey(pathname: string, key: string): boolean {
  if (!["1", "2", "3", "4"].includes(key)) {
    return false;
  }
  const path = pathname.split("?")[0] ?? pathname;
  return path === "/" || path.startsWith("/stocks");
}

function mergeLiveItems(replayItems: LivePayload[], eventItems: LivePayload[]): LivePayload[] {
  const byId = new Map<string, LivePayload>();
  for (const item of [...replayItems, ...eventItems]) {
    byId.set(item.event.event_id, item);
  }
  return [...byId.values()].sort(
    (left, right) =>
      Number(right.event.received_at_ms ?? 0) - Number(left.event.received_at_ms ?? 0),
  );
}
