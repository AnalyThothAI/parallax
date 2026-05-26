import {
  MacroWorkbenchRoute,
  parseMacroRouteTail,
} from "@features/macro";
import { useParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const { "*": routeTail } = useParams();
  const resolution = parseMacroRouteTail(routeTail);
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
