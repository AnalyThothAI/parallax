import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  getNotifications,
  getNotificationSummary,
  markAllNotificationsRead,
  markNotificationRead
} from "../../api/notifications";
import type { NotificationItem, NotificationLivePayload, NotificationSummary } from "../../api/types";
import type { MobileTask } from "../../components/MobileTaskNav";
import { useTraderStore } from "../../store/useTraderStore";

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
  token
}: UseNotificationsControllerArgs) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const runSearch = useTraderStore((state) => state.runSearch);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const summaryQuery = useQuery({
    queryKey: ["notification-summary"],
    queryFn: () => getNotificationSummary(token),
    enabled: Boolean(token),
    refetchInterval: 12_000
  });

  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getNotifications(token),
    enabled: Boolean(token),
    refetchInterval: drawerOpen ? 8_000 : 20_000
  });

  const markReadMutation = useMutation({
    mutationFn: (notificationId: string) => markNotificationRead(token, notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });

  const latestSocketNotificationId = socketNotifications[0]?.notification.notification_id ?? null;
  useEffect(() => {
    if (!latestSocketNotificationId) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["notification-summary"] });
    void queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }, [latestSocketNotificationId, queryClient]);

  const openNotification = (notification: NotificationItem) => {
    markReadMutation.mutate(notification.notification_id);
    setDrawerOpen(false);
    if (notification.entity_type === "pulse_candidate" || notification.source_table === "pulse_candidates") {
      let q: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (typeof notification.payload?.candidate_id === "string") {
        q = notification.payload.candidate_id;
      } else if (notification.source_id) {
        q = notification.source_id;
      }
      navigate(buildSignalLabUrl({ q }));
      setMobileTask("lab");
      return;
    }
    if (notification.entity_type === "social_event" || notification.source_table === "social_event_extractions") {
      let q: string | null = null;
      let handle: string | null = null;
      if (notification.symbol) {
        q = notification.symbol;
      } else if (notification.author_handle) {
        handle = normalizedHandle(notification.author_handle);
      } else if (notification.event_id) {
        q = notification.event_id;
      }
      navigate(buildSignalLabUrl({ q, handle }));
      setMobileTask("lab");
      return;
    }
    if (notification.symbol) {
      runSearch(`$${notification.symbol}`);
      navigate("/");
      setMobileTask("detail");
      return;
    }
    if (notification.author_handle) {
      runSearch(`@${notification.author_handle}`);
      navigate("/");
      setMobileTask("detail");
      return;
    }
    if (notification.event_id) {
      runSearch(notification.event_id);
      navigate("/");
      setMobileTask("detail");
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
    toggleDrawer: () => setDrawerOpen((current) => !current)
  };
}

function normalizedHandle(handle: string): string {
  return handle.trim().replace(/^@/, "").toLowerCase();
}

function buildSignalLabUrl({ q, handle }: { q?: string | null; handle?: string | null }): string {
  const params = new URLSearchParams();
  if (handle) {
    params.set("handle", handle);
  }
  if (q) {
    params.set("q", q);
  }
  const search = params.toString();
  return "/signal-lab" + (search ? "?" + search : "");
}
