import { useMemo } from "react";

import { buildRatesWorkbenchView, type RatesModuleId } from "../../model/macroRatesWorkbenchModel";
import type { MacroModulePageProps } from "../pages/MacroModulePageRenderer";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";

import { MacroRatesSubnav } from "./MacroRatesSubnav";
import { RatesCurveDiagnostics } from "./RatesCurveDiagnostics";
import { RatesDecisionSupport } from "./RatesDecisionSupport";
import { RatesDetailTables } from "./RatesDetailTables";
import { RatesDiagnosticsPanel } from "./RatesDiagnosticsPanel";
import { RatesFactStrip } from "./RatesFactStrip";
import { RatesMarketRead } from "./RatesMarketRead";
import { RatesPolicyDiagnostics } from "./RatesPolicyDiagnostics";
import { RatesPrimaryVisual } from "./RatesPrimaryVisual";
import { RatesRealRateDiagnostics } from "./RatesRealRateDiagnostics";

import "./macroRatesWorkbench.css";

export function MacroRatesModulePage({
  module,
  moduleId,
  token,
}: MacroModulePageProps & { moduleId: RatesModuleId }) {
  const ratesModuleId = moduleId;
  const view = useMemo(
    () => buildRatesWorkbenchView(module, ratesModuleId),
    [module, ratesModuleId],
  );

  if (!view.title) {
    return null;
  }

  return (
    <MacroPageScaffold label={`${view.title}模块页面`} pageKind="leaf">
      <MacroRatesSubnav activeModuleId={ratesModuleId} />
      <RatesMarketRead view={view} />
      <RatesFactStrip facts={view.facts} />
      <RatesPrimaryVisual module={module} moduleId={ratesModuleId} token={token} view={view} />
      <RatesPolicyDiagnostics diagnostics={view.policyDiagnostics} />
      <RatesCurveDiagnostics diagnostics={view.curveDiagnostics} />
      <RatesRealRateDiagnostics diagnostics={view.realRateDiagnostics} />
      <RatesDecisionSupport groups={view.decisionGroups} />
      <RatesDetailTables tables={view.detailTables} />
      <RatesDiagnosticsPanel module={module} view={view} />
    </MacroPageScaffold>
  );
}
