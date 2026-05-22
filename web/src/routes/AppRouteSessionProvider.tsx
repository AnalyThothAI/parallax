import type { AppSession } from "@app/useAppSession";
import type { ReactNode } from "react";

import { AppRouteSessionContext } from "./routeSession";

export function AppRouteSessionProvider({
  children,
  session,
}: {
  children: ReactNode;
  session: AppSession;
}) {
  return (
    <AppRouteSessionContext.Provider value={session}>{children}</AppRouteSessionContext.Provider>
  );
}
