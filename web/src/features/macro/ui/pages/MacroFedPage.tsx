import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroFedPage(props: MacroModulePageProps) {
  return <MacroModulePageFrame {...props} pageLabel="Fed" />;
}
