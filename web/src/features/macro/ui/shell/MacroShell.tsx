import type { MacroModuleView } from "@lib/types";
import type { ReactNode } from "react";

import type { MacroModuleId } from "../../model/macroRoutes";

import { MacroLocalNav } from "./MacroLocalNav";
import { MacroPageHeader } from "./MacroPageHeader";

import "./macroShell.css";

export function MacroShell({
  children,
  module,
  moduleId,
}: {
  children: ReactNode;
  module: MacroModuleView;
  moduleId: MacroModuleId;
}) {
  return (
    <section className="macro-shell" aria-label="Macro workbench">
      <MacroLocalNav moduleId={moduleId} />
      <div className="macro-shell-main">
        <MacroPageHeader module={module} moduleId={moduleId} />
        <div className="macro-shell-content">{children}</div>
      </div>
    </section>
  );
}
