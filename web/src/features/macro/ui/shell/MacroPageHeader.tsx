import type { MacroModuleView } from "@lib/types";
import { Separator } from "@shared/ui/separator";
import { Link } from "react-router-dom";

import {
  gapLabel,
  macroAsOfLabel,
  macroModuleTitle,
  macroStatusLabel,
} from "../../model/macroPageViewModel";
import {
  macroActiveSection,
  macroPrimaryTabRoutes,
  macroSecondaryTabRoutes,
  type MacroModuleId,
  type MacroNavigationRoute,
} from "../../model/macroRoutes";

import { MacroBreadcrumb } from "./MacroBreadcrumb";

export function MacroPageHeader({
  module,
  moduleId,
}: {
  module: MacroModuleView;
  moduleId: MacroModuleId;
}) {
  const gaps = module.data_gaps.slice(0, 6);
  const activeSection = macroActiveSection(moduleId);
  const primaryTabs = macroPrimaryTabRoutes();
  const secondaryTabs = macroSecondaryTabRoutes(activeSection);
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
      <nav className="macro-shell-primary-tabs" aria-label="宏观主模块">
        {primaryTabs.map((route) => (
          <MacroTabLink
            active={route.section === activeSection}
            key={route.moduleId}
            route={route}
          />
        ))}
      </nav>
      {secondaryTabs.length > 0 ? (
        <nav className="macro-shell-secondary-tabs" aria-label="宏观模块">
          {secondaryTabs.map((route) => (
            <MacroTabLink active={route.moduleId === moduleId} key={route.moduleId} route={route} />
          ))}
        </nav>
      ) : null}
      <Separator className="macro-shell-separator" />
    </header>
  );
}

function MacroTabLink({ active, route }: { active: boolean; route: MacroNavigationRoute }) {
  return (
    <Link
      aria-current={active ? "page" : undefined}
      className="macro-shell-tab"
      data-active={active ? "true" : undefined}
      to={route.href}
    >
      {route.label}
    </Link>
  );
}
