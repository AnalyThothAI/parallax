import { MacroWorkbenchRoute, parseMacroRouteTail } from "@features/macro";
import { useParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const { "*": routeTail } = useParams();
  const resolution = parseMacroRouteTail(routeTail);
  if (!resolution) {
    throw new Error("404 Not Found");
  }
  return (
    <MacroWorkbenchRoute
      moduleId={resolution.moduleId}
      pageKind={resolution.pageKind}
      productTier={resolution.productTier}
      token={token}
    />
  );
}
