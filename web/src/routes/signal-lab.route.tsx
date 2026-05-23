import { SignalLabPage } from "@features/signal-lab";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const context = useShellRouteContext();

  return (
    <SignalLabPage
      selectedAccountEventId={context.selectedAccountEventId}
      token={context.token}
      onSelectAccountEvent={context.selectAccountEvent}
    />
  );
}
