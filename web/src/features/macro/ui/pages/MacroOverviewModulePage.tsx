import {
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import {
  buildMacroWorkbenchBrief,
  buildMacroWorkbenchDiagnostics,
  buildMacroWorkbenchDrivers,
} from "../../model/macroWorkbenchModel";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroDiagnosticsPanel } from "../workbench/MacroDiagnosticsPanel";
import { MacroDriverBoard } from "../workbench/MacroDriverBoard";
import { MacroInsightBrief } from "../workbench/MacroInsightBrief";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";

export function MacroOverviewModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const brief = buildMacroWorkbenchBrief(module);
  const diagnostics = buildMacroWorkbenchDiagnostics(module, "overview");
  const drivers = buildMacroWorkbenchDrivers(module);
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });

  return (
    <MacroPageScaffold label="总览模块页面" pageKind="overview">
      <MacroInsightBrief ariaLabel="宏观简报" brief={brief} title="宏观简报" />
      <MacroMarketBoard
        ariaLabel="跨域市场板"
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
        title="跨域市场板"
      />
      <MacroDriverBoard
        ariaLabel="传导链"
        drivers={drivers}
        meta="总览"
        title="传导链"
        transmission={module.transmission}
      />
      <MacroDiagnosticsPanel diagnostics={diagnostics} source={module.provenance} />
    </MacroPageScaffold>
  );
}
