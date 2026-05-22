import "./WatchlistNotificationDot.css";

type Props = {
  count?: number;
};

export function WatchlistNotificationDot({ count = 0 }: Props) {
  if (count <= 0) {
    return null;
  }
  return (
    <span className="watchlist-notification-dot" aria-label={`${count} unread notifications`}>
      {count > 9 ? "9+" : count}
    </span>
  );
}
