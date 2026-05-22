import { PulseDetailRoutePage } from "@features/signal-lab";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();

  return <PulseDetailRoutePage token={token} />;
}
