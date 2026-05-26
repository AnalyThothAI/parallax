import { macroRouteLabel } from "../../model/macroRoutes";

import { MacroOverviewPageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroOverviewPage(props: MacroModulePageProps) {
  return <MacroOverviewPageFrame {...props} pageLabel={macroRouteLabel(props.moduleId)} />;
}
