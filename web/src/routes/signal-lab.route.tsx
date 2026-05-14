import { SignalLabPage } from "@features/signal-lab";
import type { ComponentProps } from "react";

export type SignalLabRouteProps = ComponentProps<typeof SignalLabPage>;

export function SignalLabRoute(props: SignalLabRouteProps) {
  return <SignalLabPage {...props} />;
}
