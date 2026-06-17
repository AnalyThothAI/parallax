import type { MacroModuleView } from "@lib/types";
import { useMemo } from "react";

import { buildRatesCorridorModel, type RatesCorridorModel } from "../../model/macroRatesChartModel";
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
  const fedFundsChartHasKnownSeries =
    moduleId !== "rates/fed-funds" || hasKnownFedFundsCorridorSeries(module.primary_chart);
  const series = useMacroPrimarySeries({
    chart: fedFundsChartHasKnownSeries
      ? module.primary_chart
      : { ...module.primary_chart, series: [] },
    token,
  });
  const corridorModel = useMemo(
    () => buildRatesCorridorModel(module.primary_chart, series.data),
    [module.primary_chart, series.data],
  );
  const hasChartSeries = (module.primary_chart.series?.length ?? 0) > 0;

  if (!view.chartTitle || !hasChartSeries || !fedFundsChartHasKnownSeries) {
    return null;
  }

  if (
    moduleId === "rates/fed-funds" &&
    !series.isLoading &&
    !hasRenderableCorridorModel(corridorModel)
  ) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="利率主图"
      className="macro-rates-primary-visual"
      meta={view.chartNote ?? view.readinessLabel}
      span="full"
      title="利率主图"
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

function hasKnownFedFundsCorridorSeries(chart: MacroModuleView["primary_chart"]): boolean {
  return (chart.series ?? []).some((series) => {
    const conceptKey = typeof series.concept_key === "string" ? series.concept_key : "";
    return FED_FUNDS_CORRIDOR_CONCEPTS.has(conceptKey);
  });
}

function hasRenderableCorridorModel(model: RatesCorridorModel): boolean {
  return Boolean(model.lower || model.upper || model.lines.length > 0);
}

const FED_FUNDS_CORRIDOR_CONCEPTS = new Set([
  "fed:target_lower",
  "fed:target_upper",
  "fed:effr",
  "fed:iorb",
  "liquidity:sofr",
  "fed:sofr_30d",
]);
