import { AppRoutes } from "@routes/AppRoutes";
import { IntelSocketProvider } from "@shared/socket/IntelSocketProvider";

import { useAppSession } from "./useAppSession";

export function CockpitApp() {
  const session = useAppSession();

  return (
    <IntelSocketProvider
      token={session.token}
      handles={session.bootstrapHandles.join(",")}
      replay={session.replayLimit}
      notifications
    >
      <AppRoutes session={session} />
    </IntelSocketProvider>
  );
}
