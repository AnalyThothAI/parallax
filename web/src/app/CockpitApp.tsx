import { useLiveData, useLiveRouteState } from "@features/live";
import { AppRoutes } from "@routes/AppRoutes";
import { IntelSocketProvider } from "@shared/socket/IntelSocketProvider";

export function CockpitApp() {
  const liveRoute = useLiveRouteState();
  const liveData = useLiveData({
    handles: liveRoute.handles,
    radarSortMode: liveRoute.sort,
    scope: liveRoute.scope,
    windowKey: liveRoute.window,
  });

  return (
    <IntelSocketProvider
      token={liveData.token}
      handles={liveData.handles}
      replay={liveData.replayLimit}
      notifications
    >
      <AppRoutes liveData={liveData} liveRoute={liveRoute} />
    </IntelSocketProvider>
  );
}
