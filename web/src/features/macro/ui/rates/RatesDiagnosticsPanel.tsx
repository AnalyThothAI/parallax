import type { MacroModuleView } from "@lib/types";

import type { MacroDataHealthBucket } from "../../model/macroModulePresentation";
import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroSourceTable } from "../tables/MacroSourceTable";

export function RatesDiagnosticsPanel({
  module,
  view,
}: {
  module: MacroModuleView;
  view: RatesWorkbenchView;
}) {
  const buckets = buildRatesHealthBuckets(view);
  const meta = `${view.diagnostics.moduleHealthLabel} / 全局缺口 ${view.diagnostics.globalGapReferenceCount}`;

  return (
    <>
      <MacroDataHealthPanel
        ariaLabel="利率数据诊断"
        buckets={buckets}
        meta={meta}
        title="利率数据诊断"
      />
      <MacroPanel
        ariaLabel="利率数据源状态"
        className="macro-rates-source-diagnostics"
        meta={view.diagnostics.sourceMeta ?? "来源状态"}
        title="数据源状态"
      >
        <MacroSourceTable caption="利率数据源" source={module.provenance} />
      </MacroPanel>
    </>
  );
}

function buildRatesHealthBuckets(view: RatesWorkbenchView): MacroDataHealthBucket[] {
  return [
    {
      items: view.diagnostics.coverage.map((item) => item.label),
      key: "rates_coverage",
      label: "覆盖状态",
    },
    {
      items: [],
      key: "global_gap_references",
      label: "全局缺口参考",
      referenceCount: view.diagnostics.globalGapReferenceCount,
    },
  ];
}
