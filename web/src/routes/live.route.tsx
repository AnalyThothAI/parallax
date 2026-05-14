import { LivePage, LiveRadar } from "@features/live";
import type { ComponentProps } from "react";

export type LiveRouteProps = ComponentProps<typeof LivePage>;
export type LiveRadarRouteProps = ComponentProps<typeof LiveRadar>;

export function LiveRoute(props: LiveRouteProps) {
  return <LivePage {...props} />;
}

export function LiveRadarRoute(props: LiveRadarRouteProps) {
  return <LiveRadar {...props} />;
}
