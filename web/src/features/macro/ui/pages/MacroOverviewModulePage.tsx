import { primarySupportingTable } from "../../model/macroModulePresentation";
import { macroModuleTitle } from "../../model/macroPageViewModel";
import {
  buildMacroDecisionConsole,
  buildMacroMarketEventFlow,
  buildMacroStructuredAnalysis,
  buildMacroWorkbenchBrief,
  buildMacroWorkbenchDiagnostics,
  buildMacroWorkbenchDrivers,
  hasMacroWorkbenchBrief,
  hasMacroWorkbenchDrivers,
} from "../../model/macroWorkbenchModel";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";
import { MacroDecisionConsolePanel } from "../workbench/MacroDecisionConsolePanel";
import { MacroDiagnosticsPanel } from "../workbench/MacroDiagnosticsPanel";
import { MacroDriverBoard } from "../workbench/MacroDriverBoard";
import { MacroInsightBrief } from "../workbench/MacroInsightBrief";
import { MacroMarketEventFlowPanel } from "../workbench/MacroMarketEventFlowPanel";
import { MacroStructuredAnalysisPanel } from "../workbench/MacroStructuredAnalysisPanel";

import { MacroMarketBoard } from "./MacroMarketBoard";
import type { MacroModulePageProps } from "./MacroModulePageRenderer";
import { useMacroPrimarySeries } from "./MacroPrimarySeries";

export function MacroOverviewModulePage({ module, moduleId, token }: MacroModulePageProps) {
  const brief = buildMacroWorkbenchBrief(module);
  const decisionConsole = buildMacroDecisionConsole(module);
  const structuredAnalysis = buildMacroStructuredAnalysis(module);
  const marketEventFlow = buildMacroMarketEventFlow(module);
  const diagnostics = buildMacroWorkbenchDiagnostics(module, "overview");
  const drivers = buildMacroWorkbenchDrivers(module);
  const supportingTable = primarySupportingTable(module);
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const title = macroModuleTitle(module);
  if (!title) {
    return null;
  }

  return (
    <MacroPageScaffold label={`${title}模块页面`} pageKind="overview">
      {hasMacroWorkbenchBrief(brief) ? (
        <MacroInsightBrief ariaLabel="宏观简报" brief={brief} title="宏观简报" />
      ) : null}
      <MacroDecisionConsolePanel consoleModel={decisionConsole} />
      <MacroStructuredAnalysisPanel analysis={structuredAnalysis} />
      <MacroMarketEventFlowPanel flow={marketEventFlow} />
      <MacroMarketBoard
        ariaLabel="跨域市场板"
        chart={module.primary_chart}
        moduleId={moduleId}
        seriesData={series.data}
        seriesLoading={series.isLoading}
        supportingTable={supportingTable?.rows?.length ? supportingTable : null}
        title="跨域市场板"
      />
      {hasMacroWorkbenchDrivers(drivers) ? (
        <MacroDriverBoard
          ariaLabel="传导链"
          drivers={drivers}
          meta={title}
          title="传导链"
          transmission={module.transmission}
        />
      ) : null}
      <MacroDiagnosticsPanel diagnostics={diagnostics} source={module.provenance} />
    </MacroPageScaffold>
  );
}
