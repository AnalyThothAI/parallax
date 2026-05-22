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
  if (resolution.routeKind === "asset-correlation") {
    return (
      <MacroAssetCorrelationPage
        token={token}
        onBack={() => {
          navigate("/macro/assets");
        }}
      />
    );
  }
  return <MacroWorkbenchRoute moduleId={resolution.moduleId} token={token} />;
}
