import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "@lib/types";
import { queryKeys } from "@shared/query/queryKeys";
import { signalLabPath, watchlistPath } from "@shared/routing/paths";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { MobileTask } from "../cockpit/model/mobileTask";

import {
  getNotifications,
  getNotificationSummary,
  markAllNotificationsRead,
  markNotificationRead,
} from "./api/notifications";

type UseNotificationsControllerArgs = {
  fallbackSummary?: NotificationSummary | null;
  setMobileTask: (task: MobileTask) => void;
  socketNotifications: NotificationLivePayload[];
  token: string;
};

export function useNotificationsController({
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
    enabled: Boolean(token),
    refetchInterval: 12_000,
  });

  const notificationsQuery = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: () => getNotifications(token),
    enabled: Boolean(token),
    refetchInterval: drawerOpen ? 8_000 : 20_000,
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

  const latestSocketNotificationId = socketNotifications[0]?.notification.notification_id ?? null;
  useEffect(() => {
    if (!latestSocketNotificationId) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.notificationSummary() });
    void queryClient.invalidateQueries({ queryKey: queryKeys.notifications() });
  }, [latestSocketNotificationId, queryClient]);

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
    if (
      notification.entity_type === "social_event" ||
      notification.source_table === "social_event_extractions"
    ) {
      let q: string | null = null;
      let handle: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (notification.author_handle) {
        handle = normalizedHandle(notification.author_handle);
      } else if (notification.event_id) {
        q = notification.event_id;
      }
      if (handle && !q) {
        navigate(watchlistPath({ handle }));
        setMobileTask("radar");
      } else {
        navigate(signalLabPath({ q, handle }));
        setMobileTask("lab");
      }
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

  return {
    drawerOpen,
    notifications,
    notificationSummary: summaryQuery.data?.data ?? fallbackSummary ?? null,
    notificationsLoading: notificationsQuery.isFetching && notifications.length === 0,
    markAllRead: () => markAllReadMutation.mutate(),
    markRead: (notificationId: string) => markReadMutation.mutate(notificationId),
    openNotification,
    closeDrawer: () => setDrawerOpen(false),
    toggleDrawer: () => setDrawerOpen((current) => !current),
  };
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}
