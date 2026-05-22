import { formatRelativeTime } from "@lib/format";
import type { NotificationItem, NotificationSummary } from "@lib/types";
import { IconButton } from "@shared/ui/IconButton";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { Check, CheckCheck, ExternalLink, X } from "lucide-react";

import "./NotificationDrawer.css";

type Props = {
  loading: boolean;
  notifications: NotificationItem[];
  open: boolean;
  summary?: NotificationSummary | null;
  onClose: () => void;
  onMarkAllRead: () => void;
  onMarkRead: (notificationId: string) => void;
  onOpenNotification: (notification: NotificationItem) => void;
};

export function NotificationDrawer({
  loading,
  notifications,
  open,
  summary,
  onClose,
  onMarkAllRead,
  onMarkRead,
  onOpenNotification,
}: Props) {
  if (!open) {
    return null;
  }
  return (
    <aside className="notification-drawer" aria-label="notification drawer">
      <header>
        <div>
          <span>notifications</span>
          <b>{summary?.unread_count ?? 0} unread</b>
        </div>
        <IconButton
          aria-label="mark all read"
          disabled={(summary?.unread_count ?? 0) === 0}
          onClick={onMarkAllRead}
        >
          <CheckCheck aria-hidden />
        </IconButton>
        <IconButton aria-label="close notifications" onClick={onClose}>
          <X aria-hidden />
        </IconButton>
      </header>

      <div className="notification-list">
        {loading ? (
          <RemoteState.Loading layout="inline" rows={3} label="loading notifications" />
        ) : null}
        {!loading && notifications.length === 0 ? <RemoteState.Empty title="clear" /> : null}
        {notifications.map((item) => (
          <article
            className={clsx(
              "notification-row",
              `severity-${item.severity}`,
              item.read_at_ms ? "read" : "unread",
            )}
            key={item.notification_id}
          >
            <button
              aria-label={`open ${item.title}`}
              className="notification-row-main"
              onClick={() => onOpenNotification(item)}
              type="button"
            >
              <span>{item.rule_id.replaceAll("_", " ")}</span>
              <b>{item.title}</b>
              <em>{item.body}</em>
              <small>{formatRelativeTime(item.last_seen_at_ms)}</small>
            </button>
            <div className="notification-row-actions">
              <IconButton
                aria-label={`jump to ${item.title}`}
                onClick={() => onOpenNotification(item)}
              >
                <ExternalLink aria-hidden />
              </IconButton>
              <IconButton
                aria-label={`mark ${item.title} read`}
                disabled={Boolean(item.read_at_ms)}
                onClick={() => onMarkRead(item.notification_id)}
              >
                <Check aria-hidden />
              </IconButton>
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}
