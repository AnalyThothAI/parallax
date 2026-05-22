import { MacroAssetCorrelationPage } from "./MacroAssetCorrelationPage";
import { MacroWorkbenchRoute } from "./MacroWorkbenchRoute";
import { parseMacroRouteTail, type MacroModuleId } from "./model/macroRoutes";

export type MacroPageProps = {
  moduleId?: string;
  onOpenAssetCorrelation?: () => void;
  onRouteChange?: (moduleId: MacroModuleId, sectionId?: string) => void;
  sectionId?: string;
  token: string;
};

export function MacroPage(props: MacroPageProps) {
  const resolution = parseMacroRouteTail(legacyRouteTail(props));
  if (resolution.routeKind === "asset-correlation") {
    return (
      <MacroAssetCorrelationPage
        token={props.token}
        onBack={() => props.onRouteChange?.("assets")}
      />
    );
  }
  return <MacroWorkbenchRoute moduleId={resolution.moduleId} token={props.token} />;
}

function legacyRouteTail({ moduleId, sectionId }: MacroPageProps): string | undefined {
  return [moduleId, sectionId].filter(Boolean).join("/") || undefined;
}
