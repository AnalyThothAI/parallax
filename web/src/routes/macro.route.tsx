import { MacroWorkbenchRoute, parseMacroRouteTail } from "@features/macro";
import { Navigate, useParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const { "*": routeTail } = useParams();
  const resolution = parseMacroRouteTail(routeTail);
  if (resolution.routeKind === "redirect") {
    return <Navigate replace to={resolution.canonicalPath} />;
  }
  if (resolution.routeKind === "matrix") {
    return <MacroWorkbenchRoute routeKind="matrix" token={token} />;
  }
  if (resolution.routeKind === "unsupported") {
    return (
      <MacroWorkbenchRoute routeKind="unsupported" routeTail={resolution.routeTail} token={token} />
    );
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
