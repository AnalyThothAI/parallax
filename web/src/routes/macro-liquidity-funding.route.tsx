import { MacroLiquidityFundingPage } from "@features/macro";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  return <MacroLiquidityFundingPage token={token} />;
}
