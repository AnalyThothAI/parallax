import { WatchlistPage } from "@features/watchlist";
import type { ComponentProps } from "react";

export type WatchlistRouteProps = ComponentProps<typeof WatchlistPage>;

export function WatchlistRoute(props: WatchlistRouteProps) {
  return <WatchlistPage {...props} />;
}
