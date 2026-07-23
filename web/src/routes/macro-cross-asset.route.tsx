import { MacroCrossAssetPage } from "@features/macro";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  return <MacroCrossAssetPage token={token} />;
}
