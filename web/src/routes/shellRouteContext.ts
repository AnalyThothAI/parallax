import { useOutletContext } from "react-router-dom";

import type { ShellRouteContext } from "./shellChromeData";

export function useShellRouteContext() {
  return useOutletContext<ShellRouteContext>();
}
