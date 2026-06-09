import {
  extraTables,
  primarySupportingTable,
} from "../../model/macroModulePresentation";
import { macroRouteLabel } from "../../model/macroRoutes";
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
import "./macroPages.css";

export function MacroLeafModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const brief = buildMacroWorkbenchBrief(module);
  const diagnostics = buildMacroWorkbenchDiagnostics(module, "leaf");
  const drivers = buildMacroWorkbenchDrivers(module);
  const supportingTable = primarySupportingTable(module);
  const remainingTables = extraTables(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });

  return (
    <MacroPageScaffold label={`${macroRouteLabel(moduleId)}模块页面`} pageKind="leaf">
      <MacroInsightBrief ariaLabel="模块简报" brief={brief} title="模块简报" />
      <MacroMarketBoard
        ariaLabel="主市场证据"
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable.rows?.length ? supportingTable : null}
        supportingTables={remainingTables}
        title="主市场证据"
      />
      <MacroDriverBoard
        ariaLabel="驱动与反证"
        drivers={drivers}
        meta={macroRouteLabel(moduleId)}
        title="驱动与反证"
        transmission={module.transmission}
      />
      <MacroDiagnosticsPanel diagnostics={diagnostics} source={module.provenance} />
    </MacroPageScaffold>
  );
}
