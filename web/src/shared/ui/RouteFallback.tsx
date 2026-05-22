import * as PageState from "./PageState";

export function RouteFallback() {
  return <PageState.Loading layout="route" rows={4} label="loading route" />;
}
