import {
  MacroAssetCorrelationPage,
  MacroWorkbenchRoute,
  parseMacroRouteTail,
} from "@features/macro";
import { useNavigate, useParams } from "react-router-dom";

export function MacroRoute({ token }: { token: string }) {
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
