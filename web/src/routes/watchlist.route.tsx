import { WatchlistPage } from "@features/watchlist";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();

  return (
    <WatchlistPage
      accountUnreadCounts={context.accountUnreadCounts}
      handles={context.configuredWatchlistHandles}
      token={context.token}
      onMarkHandleRead={context.onMarkHandleRead}
    />
  );
}
