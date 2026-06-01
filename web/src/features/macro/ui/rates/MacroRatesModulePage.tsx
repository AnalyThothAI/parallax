import { useMemo } from "react";

import { buildRatesWorkbenchView, type RatesModuleId } from "../../model/macroRatesWorkbenchModel";
import type { MacroModulePageProps } from "../pages/MacroModulePageRenderer";
import { MacroPageScaffold } from "../primitives/MacroPageScaffold";

import { MacroRatesSubnav } from "./MacroRatesSubnav";
import { RatesDecisionSupport } from "./RatesDecisionSupport";
import { RatesDetailTables } from "./RatesDetailTables";
import { RatesDiagnosticsPanel } from "./RatesDiagnosticsPanel";
import { RatesFactStrip } from "./RatesFactStrip";
import { RatesMarketRead } from "./RatesMarketRead";
import { RatesPrimaryVisual } from "./RatesPrimaryVisual";

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

  return (
    <MacroPageScaffold label={`${view.title}利率工作台`} pageKind="leaf">
      <MacroRatesSubnav activeModuleId={ratesModuleId} />
      <RatesMarketRead view={view} />
      <RatesFactStrip facts={view.facts} />
      <RatesPrimaryVisual module={module} moduleId={ratesModuleId} token={token} view={view} />
      <RatesDecisionSupport groups={view.decisionGroups} />
      <RatesDetailTables tables={view.detailTables} />
      <RatesDiagnosticsPanel module={module} view={view} />
    </MacroPageScaffold>
  );
}
