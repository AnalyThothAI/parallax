import { EquityEventsRoute, parseEquityEventRouteState } from "@features/equity-events";
import { useParams, useSearchParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const [searchParams] = useSearchParams();
  const { "*": routeTail } = useParams();
  const routeState = parseEquityEventRouteState(searchParams, routeTail ?? "");
  return <EquityEventsRoute routeState={routeState} token={token} />;
}
