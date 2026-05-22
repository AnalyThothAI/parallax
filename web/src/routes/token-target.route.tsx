import { TokenCaseRoute } from "@features/token-case";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();

  return <TokenCaseRoute token={token} />;
}
