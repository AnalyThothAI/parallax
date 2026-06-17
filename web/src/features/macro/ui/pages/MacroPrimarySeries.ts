import type { MacroModuleChart } from "@lib/types";

import { useMacroSeriesQuery } from "../../api/useMacroSeriesQuery";
import { chartConceptKeys, chartIdentifier } from "../../model/macroModulePageModel";

export function useMacroPrimarySeries({
  chart,
  token,
}: {
  chart: MacroModuleChart;
  token: string;
}) {
  const seriesConceptKeys = chartConceptKeys(chart);
  const shouldFetchSeries =
    Boolean(chartIdentifier(chart)) && seriesConceptKeys.length > 0 && !isYieldCurveChart(chart);
  return useMacroSeriesQuery({
    conceptKeys: shouldFetchSeries ? seriesConceptKeys : [],
    token,
    window: "60d",
  });
}

function isYieldCurveChart(chart: MacroModuleChart): boolean {
  return Boolean(chartIdentifier(chart)?.includes("curve"));
}
