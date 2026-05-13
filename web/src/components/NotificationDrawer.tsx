import type { NotificationItem, NotificationSummary } from "@lib/types";
import { Check, CheckCheck, ExternalLink, X } from "lucide-react";

import { formatRelativeTime } from "../lib/format";

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
        <button
          aria-label="mark all read"
          className="icon-button"
          disabled={(summary?.unread_count ?? 0) === 0}
          onClick={onMarkAllRead}
          type="button"
        >
          <CheckCheck aria-hidden />
        </button>
        <button
          aria-label="close notifications"
          className="icon-button"
          onClick={onClose}
          type="button"
        >
          <X aria-hidden />
        </button>
      </header>

      <div className="notification-list">
        {loading ? <div className="notification-empty">loading</div> : null}
        {!loading && notifications.length === 0 ? (
          <div className="notification-empty">clear</div>
        ) : null}
        {notifications.map((item) => (
          <article
            className={`notification-row severity-${item.severity} ${item.read_at_ms ? "read" : "unread"}`}
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
              <button
                aria-label={`jump to ${item.title}`}
                className="icon-button"
                onClick={() => onOpenNotification(item)}
                type="button"
              >
                <ExternalLink aria-hidden />
              </button>
              <button
                aria-label={`mark ${item.title} read`}
                className="icon-button"
                disabled={Boolean(item.read_at_ms)}
                onClick={() => onMarkRead(item.notification_id)}
                type="button"
              >
                <Check aria-hidden />
              </button>
            </div>
          </article>
        ))}
      </div>
    </aside>
  );
}
