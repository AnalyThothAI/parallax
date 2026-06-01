import type { MacroModuleView } from "@lib/types";
import { useMemo } from "react";

import { buildRatesCorridorModel } from "../../model/macroRatesChartModel";
import type { RatesModuleId, RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroYieldCurveChart } from "../charts/MacroYieldCurveChart";
import { MacroPrimaryChart } from "../pages/MacroMarketBoard";
import { useMacroPrimarySeries } from "../pages/MacroPrimarySeries";
import { MacroPanel } from "../primitives/MacroPanel";

import { RatesCorridorChart } from "./RatesCorridorChart";

export function RatesPrimaryVisual({
  module,
  moduleId,
  token,
  view,
}: {
  module: MacroModuleView;
  moduleId: RatesModuleId;
  token: string;
  view: RatesWorkbenchView;
}) {
  const series = useMacroPrimarySeries({ chart: module.primary_chart, token });
  const corridorModel = useMemo(
    () => buildRatesCorridorModel(module.primary_chart, series.data),
    [module.primary_chart, series.data],
  );

  return (
    <MacroPanel
      ariaLabel="主要图表"
      className="macro-rates-primary-visual"
      meta={view.chartNote ?? view.readinessLabel}
      span="full"
      title="主要图表"
    >
      <div className="macro-rates-chart-copy">
        <h3>{view.chartTitle}</h3>
        {view.chartNote ? <p>{view.chartNote}</p> : null}
        {view.proxyNote ? <p>{view.proxyNote}</p> : null}
      </div>
      {moduleId === "rates/fed-funds" ? (
        series.isLoading ? (
          <div
            aria-label={`${view.chartTitle}加载状态`}
            className="macro-rates-chart-loading"
            role="status"
          >
            图表序列加载中
          </div>
        ) : (
          <RatesCorridorChart model={corridorModel} />
        )
      ) : moduleId === "rates/yield-curve" ? (
        <MacroYieldCurveChart chart={module.primary_chart} title={view.chartTitle} />
      ) : (
        <MacroPrimaryChart
          chart={module.primary_chart}
          moduleId={moduleId}
          seriesData={series.data}
          seriesLoading={series.isLoading}
        />
      )}
    </MacroPanel>
  );
}
