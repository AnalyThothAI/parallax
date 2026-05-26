import type { MacroModuleView } from "@lib/types";

import type { MacroPageKind } from "../../model/macroPageRegistry";
import type { MacroModuleId } from "../../model/macroRoutes";

import { MacroAssetIndexPage } from "./MacroAssetIndexPage";
import { MacroLeafModulePage } from "./MacroLeafModulePage";
import { MacroModuleIndexPage } from "./MacroModuleIndexPage";
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
  if (props.pageKind === "index" && props.moduleId === "assets") {
    return <MacroAssetIndexPage {...props} />;
  }
  if (props.pageKind === "index") {
    return <MacroModuleIndexPage {...props} />;
  }
  return <MacroLeafModulePage {...props} />;
}
