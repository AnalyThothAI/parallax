import { tableCaption } from "../../model/macroModulePageModel";
import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  buildMacroMetrics,
  extraTables,
  macroReadSummary,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroStatusLabel } from "../../model/macroPageViewModel";
import { macroRouteLabel } from "../../model/macroRoutes";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroEvidencePanel } from "../primitives/MacroEvidencePanel";
import { MacroMetricStrip } from "../primitives/MacroMetricStrip";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroReadPanel } from "../primitives/MacroReadPanel";
import { MacroTransmissionPanel } from "../primitives/MacroTransmissionPanel";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";
import "./macroPages.css";

export function MacroLeafModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const metrics = buildMacroMetrics({ tiles: module.tiles });
  const supportingTable = primarySupportingTable(module);
  const remainingTables = extraTables(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const evidenceGroups = buildMacroEvidenceGroups(module.module_evidence);
  const dataHealthBuckets = buildMacroDataHealthBuckets(module.data_health, "leaf");

  return (
    <MacroPageScaffold label={`${macroRouteLabel(moduleId)}模块页面`} pageKind="leaf">
      <MacroMetricStrip
        ariaLabel="关键指标"
        density={metrics.length > 4 ? "compact" : "card"}
        metrics={metrics}
      />
      <MacroMarketBoard
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
      />
      {remainingTables.length > 0 ? (
        <MacroPanel
          ariaLabel="数据可用性与代理说明"
          meta={String(remainingTables.length)}
          span="full"
          title="数据可用性 / 代理说明"
        >
          {remainingTables.map((table) => (
            <MacroDataTable
              caption={tableCaption(table)}
              key={String(table.id ?? tableCaption(table))}
              table={table}
            />
          ))}
        </MacroPanel>
      ) : null}
      <MacroReadPanel
        meta={macroStatusLabel(module)}
        read={module.module_read}
        summary={macroReadSummary(module)}
      />
      <MacroTransmissionPanel meta={macroRouteLabel(moduleId)} nodes={module.transmission} />
      <MacroEvidencePanel groups={evidenceGroups} />
      <MacroPanel
        ariaLabel="数据来源"
        meta={module.snapshot.projection_version}
        span="half"
        title="数据来源"
      >
        <MacroSourceTable caption="数据源" source={module.provenance} />
      </MacroPanel>
      <MacroDataHealthPanel
        buckets={dataHealthBuckets}
        meta={module.data_health.summary_label ?? module.data_health.summary_status}
      />
    </MacroPageScaffold>
  );
}
