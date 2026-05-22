import type { MacroModuleChart, MacroSeriesData } from "@lib/types";
import { useMemo } from "react";

import { buildMacroNormalizedReturnModel } from "../../model/macroChartModel";

import { MacroLineChartFigure } from "./MacroTimeSeriesChart";

export function MacroNormalizedReturnChart({
  chart,
  seriesData,
  title,
}: {
  chart: MacroModuleChart;
  seriesData?: MacroSeriesData | null;
  title: string;
}) {
  const model = useMemo(
    () => buildMacroNormalizedReturnModel(chart, seriesData),
    [chart, seriesData],
  );
  return <MacroLineChartFigure model={model} title={title} valueUnit="return_percent" />;
}
