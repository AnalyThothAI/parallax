import { MacroOverviewPage } from "@features/macro";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  return <MacroOverviewPage token={token} />;
}
