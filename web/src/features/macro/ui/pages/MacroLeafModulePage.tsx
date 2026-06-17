import { extraTables, primarySupportingTable } from "../../model/macroModulePresentation";
import { macroRouteLabel } from "../../model/macroRoutes";
import {
  buildMacroAssetClassDiagnostics,
  buildMacroCreditDiagnostics,
  buildMacroEmploymentDiagnostics,
  buildMacroGrowthDiagnostics,
  buildMacroInflationDiagnostics,
  buildMacroLiquidityDiagnostics,
  buildMacroVolatilityDiagnostics,
  buildMacroWorkbenchBrief,
  buildMacroWorkbenchDiagnostics,
  buildMacroWorkbenchDrivers,
  hasMacroWorkbenchBrief,
  hasMacroWorkbenchDrivers,
} from "../../model/macroWorkbenchModel";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroDiagnosticsPanel } from "../workbench/MacroDiagnosticsPanel";
import { MacroDriverBoard } from "../workbench/MacroDriverBoard";
import { MacroInsightBrief } from "../workbench/MacroInsightBrief";
import { MacroSignalDiagnosticsPanel } from "../workbench/MacroSignalDiagnosticsPanel";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";
import "./macroPages.css";

export function MacroLeafModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const brief = buildMacroWorkbenchBrief(module);
  const assetClassDiagnostics = buildMacroAssetClassDiagnostics(module);
  const creditDiagnostics = buildMacroCreditDiagnostics(module);
  const employmentDiagnostics = buildMacroEmploymentDiagnostics(module);
  const growthDiagnostics = buildMacroGrowthDiagnostics(module);
  const inflationDiagnostics = buildMacroInflationDiagnostics(module);
  const liquidityDiagnostics = buildMacroLiquidityDiagnostics(module);
  const volatilityDiagnostics = buildMacroVolatilityDiagnostics(module);
  const diagnostics = buildMacroWorkbenchDiagnostics(module, "leaf");
  const drivers = buildMacroWorkbenchDrivers(module);
  const supportingTable = primarySupportingTable(module);
  const remainingTables = extraTables(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });

  return (
    <MacroPageScaffold label={`${macroRouteLabel(moduleId)}模块页面`} pageKind="leaf">
      {hasMacroWorkbenchBrief(brief) ? (
        <MacroInsightBrief ariaLabel="模块简报" brief={brief} title="模块简报" />
      ) : null}
      <MacroMarketBoard
        ariaLabel="主市场证据"
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable?.rows?.length ? supportingTable : null}
        supportingTables={remainingTables}
        title="主市场证据"
      />
      <MacroSignalDiagnosticsPanel diagnostics={liquidityDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={assetClassDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={growthDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={employmentDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={inflationDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={creditDiagnostics} />
      <MacroSignalDiagnosticsPanel diagnostics={volatilityDiagnostics} />
      {hasMacroWorkbenchDrivers(drivers) ? (
        <MacroDriverBoard
          ariaLabel="驱动与反证"
          drivers={drivers}
          meta={macroRouteLabel(moduleId)}
          title="驱动与反证"
          transmission={module.transmission}
        />
      ) : null}
      <MacroDiagnosticsPanel diagnostics={diagnostics} source={module.provenance} />
    </MacroPageScaffold>
  );
}
