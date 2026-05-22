import { useAppSession } from "@app/useAppSession";
import { AppRouteSessionProvider } from "@routes/AppRouteSessionProvider";
import { createAppMemoryRouter } from "@routes/router";
import { RouteFallback } from "@shared/ui/RouteFallback";
import { useMemo } from "react";
import { RouterProvider } from "react-router-dom";

import { renderWithProviders } from "./renderWithProviders";

export function renderAppRoute(route = "/") {
  return renderWithProviders(<TestRouteApp route={route} />, { withRouter: false });
}

function TestRouteApp({ route }: { route: string }) {
  const session = useAppSession();
  const router = useMemo(() => createAppMemoryRouter({ initialEntries: [route] }), [route]);

  return (
    <AppRouteSessionProvider session={session}>
      <RouterProvider router={router} fallbackElement={<RouteFallback />} />
    </AppRouteSessionProvider>
  );
}
