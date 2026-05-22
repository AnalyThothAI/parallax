import type { MacroModuleView } from "@lib/types";
import { Separator } from "@shared/ui/separator";

import {
  gapLabel,
  macroAsOfLabel,
  macroModuleTitle,
  macroStatusLabel,
} from "../../model/macroPageViewModel";
import type { MacroModuleId } from "../../model/macroRoutes";

import { MacroBreadcrumb } from "./MacroBreadcrumb";

export function MacroPageHeader({
  module,
  moduleId,
}: {
  module: MacroModuleView;
  moduleId: MacroModuleId;
}) {
  const gaps = module.data_gaps.slice(0, 6);
  return (
    <header className="macro-shell-header">
      <MacroBreadcrumb moduleId={moduleId} />
      <div className="macro-shell-heading-row">
        <div>
          <span className="macro-shell-kicker">宏观工作台</span>
          <h2>{macroModuleTitle(moduleId, module)}</h2>
        </div>
        <div className="macro-shell-state" aria-label="模块状态">
          <span>{macroAsOfLabel(module)}</span>
          <strong>{macroStatusLabel(module)}</strong>
        </div>
      </div>
      {gaps.length > 0 ? (
        <div className="macro-shell-gap-strip" aria-label="数据缺口">
          {gaps.map((gap) => (
            <span key={gapLabel(gap)}>{gapLabel(gap)}</span>
          ))}
        </div>
      ) : null}
      <Separator className="macro-shell-separator" />
    </header>
  );
}
