import type { NotificationItem, NotificationLivePayload } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { searchPath, watchlistPath } from "@shared/routing/paths";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getNotifications,
  markAllNotificationsRead,
  markAuthorNotificationsRead,
  markNotificationRead,
} from "./api/notifications";

type UseNotificationsControllerArgs = {
  enabled?: boolean;
  socketNotifications: NotificationLivePayload[];
  token: string;
};

export function useNotificationsController({
  enabled = true,
  socketNotifications,
  token,
}: UseNotificationsControllerArgs) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const notificationsQuery = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: () => getNotifications(token),
    enabled: Boolean(token) && enabled,
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(token, notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
    },
  });

  const { mutate: markAuthorReadMutate } = useMutation({
    mutationFn: (handle: string) => markAuthorNotificationsRead(token, handle),
    onSuccess: () => {
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
    if (!latestSocketNotificationId) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
  }, [latestSocketNotificationId, queryClient]);

  const openNotification = (notification: NotificationItem) => {
    markReadMutation.mutate(notification.notification_id);
    setDrawerOpen(false);
    if (notification.symbol) {
      navigate(searchPath({ q: notification.symbol }));
      return;
    }
    if (notification.author_handle) {
      navigate(watchlistPath({ handle: normalizedHandle(notification.author_handle) }));
      return;
    }
    if (notification.event_id) {
      navigate(searchPath({ q: notification.event_id }));
    }
  };

  const notifications = notificationsQuery.data?.data.items ?? [];

  return {
    drawerOpen,
    notifications,
    notificationSummary: notificationsQuery.data?.data.summary ?? null,
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
