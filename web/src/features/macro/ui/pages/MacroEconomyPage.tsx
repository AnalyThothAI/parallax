import { macroRouteLabel } from "../../model/macroRoutes";

import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroEconomyPage(props: MacroModulePageProps) {
  return <MacroModulePageFrame {...props} pageLabel={macroRouteLabel(props.moduleId)} />;
}
