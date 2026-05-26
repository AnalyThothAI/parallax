import {
  buildMacroDataHealthBuckets,
  buildMacroMetrics,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroReadPanel } from "../primitives/MacroReadPanel";
import { MacroTransmissionPanel } from "../primitives/MacroTransmissionPanel";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";

export function MacroOverviewModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "overview");

  return (
    <MacroPageScaffold label="总览模块页面" pageKind="overview">
      <MacroReadPanel
        ariaLabel="宏观总览"
        meta={macroStatusLabel(module)}
        read={module.module_read}
        summary={macroReadSummary(module)}
        title="宏观总览"
      />
      <MacroMetricStrip ariaLabel="关键指标" density="compact" metrics={metrics.slice(0, 6)} />
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
        title="核心驱动"
      />
      <MacroTransmissionPanel
        ariaLabel="全局传导链"
        meta="总览"
        nodes={module.transmission}
        title="全局传导链"
      />
      <MacroDataHealthPanel
        ariaLabel="数据健康"
        buckets={dataHealthBuckets}
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
        title="数据健康"
      />
    </MacroPageScaffold>
  );
}
