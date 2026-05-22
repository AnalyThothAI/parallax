import { StocksRadarPage } from "@features/stocks";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();

  return (
    <StocksRadarPage
      scope={context.scope}
      token={context.token}
      windowKey={context.windowKey}
      onScopeChange={context.updateScope}
      onWindowChange={context.updateWindow}
    />
  );
}
