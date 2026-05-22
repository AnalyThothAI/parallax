import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroOverviewPage(props: MacroModulePageProps) {
  return <MacroModulePageFrame {...props} pageLabel="Overview" />;
}
