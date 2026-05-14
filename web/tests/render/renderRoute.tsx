import { App } from "../../src/App";

import { renderWithProviders } from "./renderWithProviders";

export function renderAppRoute(route = "/") {
  return renderWithProviders(<App />, { route });
}
