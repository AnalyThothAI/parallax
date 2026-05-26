import type { MacroModuleView } from "@lib/types";
import { Separator } from "@shared/ui/separator";

import {
  macroAsOfLabel,
  macroModuleTitle,
  macroStatusLabel,
} from "../../model/macroPageViewModel";
import { type MacroModuleId } from "../../model/macroRoutes";

import { MacroBreadcrumb } from "./MacroBreadcrumb";

export function MacroPageHeader({
  module,
  moduleId,
}: {
  module: MacroModuleView;
  moduleId: MacroModuleId;
}) {
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
      <Separator className="macro-shell-separator" />
    </header>
  );
}

function historyReadinessLabel(module: MacroModuleView): string {
  const dataHealthStatus = stringValue(module.data_health?.summary_status);
  if (dataHealthStatus) {
    return readyDataHealthStatuses.has(dataHealthStatus) ? "历史样本就绪" : "历史样本不足";
  }
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

const readyDataHealthStatuses = new Set(["ok", "ready", "current", "complete"]);
