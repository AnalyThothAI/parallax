import { macroRouteLabel } from "../../model/macroRoutes";

import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroRatesPage(props: MacroModulePageProps) {
  return <MacroModulePageFrame {...props} pageLabel={macroRouteLabel(props.moduleId)} />;
}
