import { Bell } from "lucide-react";

import type { NotificationSummary } from "../api/types";

type Props = {
  summary?: NotificationSummary | null;
  open: boolean;
  onClick: () => void;
};

export function NotificationBell({ summary, open, onClick }: Props) {
  const unread = summary?.unread_count ?? 0;
  const hasHigh = Boolean(
    (summary?.high_unread_count ?? 0) > 0 || (summary?.critical_unread_count ?? 0) > 0,
  );
  return (
    <button
      aria-label="notifications"
      aria-pressed={open}
      className={`notification-bell ${open ? "open" : ""} ${unread > 0 ? "has-unread" : ""} ${hasHigh ? "has-high" : ""}`}
      onClick={onClick}
      title="Notifications"
      type="button"
    >
      <Bell aria-hidden />
      {unread > 0 ? <span>{unread > 99 ? "99+" : unread}</span> : null}
    </button>
  );
}
