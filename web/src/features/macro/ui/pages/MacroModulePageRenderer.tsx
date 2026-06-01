import type { MacroModuleView } from "@lib/types";

import type { MacroPageKind } from "../../model/macroPageRegistry";
import { isRatesModuleId } from "../../model/macroRatesWorkbenchModel";
import type { MacroModuleId } from "../../model/macroRoutes";
import { MacroRatesModulePage } from "../rates/MacroRatesModulePage";

import { MacroLeafModulePage } from "./MacroLeafModulePage";
import { MacroOverviewModulePage } from "./MacroOverviewModulePage";

export type MacroModulePageProps = {
  module: MacroModuleView;
  moduleId: MacroModuleId;
  pageKind: MacroPageKind;
  token: string;
};

export function MacroModulePageRenderer(props: MacroModulePageProps) {
  if (props.pageKind === "overview") {
    return <MacroOverviewModulePage {...props} />;
  }
  if (isRatesModuleId(props.moduleId)) {
    return <MacroRatesModulePage {...props} moduleId={props.moduleId} />;
  }
  return <MacroLeafModulePage {...props} />;
}
