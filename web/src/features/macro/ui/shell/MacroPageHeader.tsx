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
  const question = stringValue(module.snapshot.question) ?? stringValue(module.snapshot.subtitle);
  return (
    <header className="macro-shell-header">
      <MacroBreadcrumb moduleId={moduleId} />
      <div className="macro-shell-heading-row">
        <div>
          <span className="macro-shell-kicker">宏观工作台</span>
          <h1>{macroModuleTitle(moduleId, module)}</h1>
          {question ? <p>{question}</p> : null}
        </div>
        <div className="macro-shell-state" aria-label="模块状态">
          <span>状态</span>
          <strong>{macroStatusLabel(module)}</strong>
          <span>{macroAsOfLabel(module)}</span>
          <strong>{historyReadinessLabel(module)}</strong>
        </div>
      </div>
      {gaps.length > 0 ? (
        <div className="macro-shell-gap-strip" aria-label="数据缺口">
          {gaps.map((gap, index) => (
            <span key={`${index}:${gapLabel(gap)}`}>{gapLabel(gap)}</span>
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

function historyReadinessLabel(module: MacroModuleView): string {
  const requiredPoints = numberValue(module.primary_chart.min_points) ?? 2;
  const pointCounts = chartPointCounts(module);
  if (pointCounts.length > 0 && Math.min(...pointCounts) < requiredPoints) {
    return "历史样本不足";
  }
  if (module.primary_chart.status === "insufficient_history") {
    return "历史样本不足";
  }
  return "历史样本就绪";
}

function chartPointCounts(module: MacroModuleView): number[] {
  const counts = (module.primary_chart.series ?? [])
    .map((series) => numberValue(series.point_count))
    .filter((count): count is number => count !== null);
  if (counts.length > 0) {
    return counts;
  }
  return module.tiles
    .map((tile) => numberValue(tile.history_points))
    .filter((count): count is number => count !== null);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
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
