import { MacroRatesInflationPage } from "@features/macro";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  return <MacroRatesInflationPage token={token} />;
}
