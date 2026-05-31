import type { LiveMobileTask } from "@features/live";
import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { signalLabPath, watchlistPath } from "@shared/routing/paths";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getNotifications,
  getNotificationSummary,
  markAllNotificationsRead,
  markAuthorNotificationsRead,
  markNotificationRead,
} from "./api/notifications";

type UseNotificationsControllerArgs = {
  enabled?: boolean;
  fallbackSummary?: NotificationSummary | null;
  setMobileTask: (task: LiveMobileTask) => void;
  socketNotifications: NotificationLivePayload[];
  token: string;
};

export function useNotificationsController({
  enabled = true,
  fallbackSummary,
  setMobileTask,
  socketNotifications,
  token,
}: UseNotificationsControllerArgs) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const summaryQuery = useQuery({
    queryKey: queryKeys.notificationSummary(),
    queryFn: () => getNotificationSummary(token),
    enabled: Boolean(token) && enabled && drawerOpen,
  });

  const notificationsQuery = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: () => getNotifications(token),
    enabled: Boolean(token) && enabled && drawerOpen,
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(token, notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
    },
  });

  const { mutate: markAuthorReadMutate } = useMutation({
    mutationFn: (handle: string) => markAuthorNotificationsRead(token, handle),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
    },
  });

  const markAuthorRead = useCallback(
    (handle: string) => {
      markAuthorReadMutate(handle);
    },
    [markAuthorReadMutate],
  );

  const latestSocketNotificationId = socketNotifications[0]?.notification.notification_id ?? null;
  useEffect(() => {
    if (!latestSocketNotificationId || !drawerOpen) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
  }, [drawerOpen, latestSocketNotificationId, queryClient]);

  const openNotification = (notification: NotificationItem) => {
    markReadMutation.mutate(notification.notification_id);
    setDrawerOpen(false);
    if (
      notification.entity_type === "pulse_candidate" ||
      notification.source_table === "pulse_candidates"
    ) {
      let q: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (typeof notification.payload?.candidate_id === "string") {
        q = notification.payload.candidate_id;
      } else if (notification.source_id) {
        q = notification.source_id;
      }
      navigate(signalLabPath({ q }));
      setMobileTask("lab");
      return;
    }
    if (notification.symbol) {
      navigate(signalLabPath({ q: notification.symbol }));
      setMobileTask("lab");
      return;
    }
    if (notification.author_handle) {
      navigate(watchlistPath({ handle: normalizedHandle(notification.author_handle) }));
      setMobileTask("radar");
      return;
    }
    if (notification.event_id) {
      navigate(signalLabPath({ q: notification.event_id }));
      setMobileTask("lab");
    }
  };

  const notifications = notificationsQuery.data?.data.items ?? [];
  const socketSummary = summaryFromSocketNotifications(socketNotifications);

  return {
    drawerOpen,
    notifications,
    notificationSummary:
      summaryQuery.data?.data ??
      notificationsQuery.data?.data.summary ??
      socketSummary ??
      fallbackSummary ??
      null,
    notificationsLoading: notificationsQuery.isFetching && notifications.length === 0,
    markAllRead: () => markAllReadMutation.mutate(),
    markAuthorRead,
    markRead: (notificationId: string) => markReadMutation.mutate(notificationId),
    openNotification,
    closeDrawer: () => setDrawerOpen(false),
    toggleDrawer: () => setDrawerOpen((current) => !current),
  };
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function summaryFromSocketNotifications(
  socketNotifications: NotificationLivePayload[],
): NotificationSummary | null {
  if (!socketNotifications.length) {
    return null;
  }
  const accountUnreadCounts: Record<string, number> = {};
  let highUnreadCount = 0;
  let criticalUnreadCount = 0;
  let unreadCount = 0;
  let highestUnreadSeverity: NotificationSummary["highest_unread_severity"] = null;

  for (const item of socketNotifications) {
    const notification = item.notification;
    if (notification.read_at_ms) {
      continue;
    }
    unreadCount += 1;
    if (notification.severity === "high") highUnreadCount += 1;
    if (notification.severity === "critical") criticalUnreadCount += 1;
    if (
      highestUnreadSeverity === null ||
      severityRank(notification.severity) > severityRank(highestUnreadSeverity)
    ) {
      highestUnreadSeverity = notification.severity;
    }
    const handle = normalizedHandle(notification.author_handle ?? "");
    if (handle) {
      accountUnreadCounts[handle] = (accountUnreadCounts[handle] ?? 0) + 1;
    }
  }

  if (unreadCount === 0) {
    return null;
  }

  return {
    subscriber_key: "local",
    unread_count: unreadCount,
    high_unread_count: highUnreadCount,
    critical_unread_count: criticalUnreadCount,
    highest_unread_severity: highestUnreadSeverity,
    account_unread_counts: accountUnreadCounts,
  };
}

function severityRank(severity: string | null | undefined): number {
  if (severity === "critical") return 3;
  if (severity === "high") return 2;
  if (severity === "warning") return 1;
  return 0;
}
