import { StocksRadarPage } from "@features/stocks";
import type { ComponentProps } from "react";

export type StocksRouteProps = ComponentProps<typeof StocksRadarPage>;

export function StocksRoute(props: StocksRouteProps) {
  return <StocksRadarPage {...props} />;
}
