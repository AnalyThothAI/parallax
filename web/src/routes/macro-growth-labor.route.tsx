import { MacroGrowthLaborPage } from "@features/macro";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  return <MacroGrowthLaborPage token={token} />;
}
