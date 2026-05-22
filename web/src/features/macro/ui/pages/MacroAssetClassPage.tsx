import { macroRouteLabel } from "../../model/macroRoutes";

import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroAssetClassPage(props: MacroModulePageProps) {
  return <MacroModulePageFrame {...props} pageLabel={macroRouteLabel(props.moduleId)} />;
}
