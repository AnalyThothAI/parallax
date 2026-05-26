import {
  MacroAssetCorrelationPage,
  MacroWorkbenchRoute,
  parseMacroRouteTail,
} from "@features/macro";
import { useNavigate, useParams } from "react-router-dom";

import { useShellRouteContext } from "./shellRouteContext";

export function Component() {
  const { token } = useShellRouteContext();
  const navigate = useNavigate();
  const { "*": routeTail } = useParams();
  const resolution = parseMacroRouteTail(routeTail);
  if (resolution.routeKind === "matrix") {
    return (
      <MacroAssetCorrelationPage
        token={token}
        onBack={() => {
          navigate("/macro/assets");
        }}
      />
    );
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
