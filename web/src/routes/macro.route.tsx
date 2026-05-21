import { MacroAssetCorrelationPage, MacroPage } from "@features/macro";
import { useNavigate, useParams } from "react-router-dom";

export function MacroRoute({ token }: { token: string }) {
  const navigate = useNavigate();
  const { "*": routeTail } = useParams();
  const [moduleId, sectionId] = routeTail?.split("/").filter(Boolean) ?? [];
  if (moduleId === "assets" && sectionId === "correlation") {
    return (
      <MacroAssetCorrelationPage
        token={token}
        onBack={() => {
          navigate("/macro/assets");
        }}
      />
    );
  }
  return (
    <MacroPage
      moduleId={moduleId}
      sectionId={sectionId}
      token={token}
      onOpenAssetCorrelation={() => {
        navigate("/macro/assets/correlation");
      }}
      onRouteChange={(nextModuleId, nextSectionId) => {
        navigate(macroPath(nextModuleId, nextSectionId));
      }}
    />
  );
}

function macroPath(moduleId: string, sectionId?: string): string {
  if (moduleId === "overview" && !sectionId) {
    return "/macro";
  }
  if (!sectionId) {
    return `/macro/${moduleId}`;
  }
  return `/macro/${moduleId}/${sectionId}`;
}
