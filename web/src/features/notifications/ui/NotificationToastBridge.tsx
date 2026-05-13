import type { NotificationItem } from "@lib/types";
import { useEffect, useRef } from "react";
import { Toaster, toast } from "sonner";


type Props = {
  notifications: NotificationItem[];
  onOpenNotification: (notification: NotificationItem) => void;
};

export function NotificationToastBridge({ notifications, onOpenNotification }: Props) {
  const seen = useRef(new Set<string>());

  useEffect(() => {
    for (const notification of notifications) {
      if (seen.current.has(notification.notification_id)) {
        continue;
      }
      seen.current.add(notification.notification_id);
      if (notification.severity !== "high" && notification.severity !== "critical") {
        continue;
      }
      toast(notification.title, {
        description: notification.body,
        action: {
          label: "Open",
          onClick: () => onOpenNotification(notification),
        },
      });
    }
  }, [notifications, onOpenNotification]);

  return <Toaster closeButton position="top-right" richColors theme="dark" />;
}
