import type { MacroModuleView } from "@lib/types";

import { tableCaption } from "../../model/macroModulePageModel";
import type { MacroDataHealthBucket } from "../../model/macroModulePresentation";
import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
import { MacroDataHealthPanel } from "../primitives/MacroDataHealthPanel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroDataTable } from "../tables/MacroDataTable";
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
  const diagnosticTables = view.detailTables.filter(
    (entry) => entry.role === "diagnostic" && (entry.table.rows?.length ?? 0) > 0,
  );

  return (
    <div className="macro-rates-diagnostics">
      <MacroDataHealthPanel
        ariaLabel="利率数据诊断"
        buckets={buckets}
        meta={meta}
        title="利率数据诊断"
      />
      {diagnosticTables.length > 0 ? (
        <MacroPanel
          ariaLabel="利率诊断明细"
          className="macro-rates-diagnostic-tables"
          meta={`${diagnosticTables.length} 张`}
          title="诊断明细"
        >
          <div className="macro-rates-table-stack">
            {diagnosticTables.map(({ table }) => (
              <MacroDataTable
                caption={tableCaption(table)}
                key={String(table.id ?? tableCaption(table))}
                table={table}
              />
            ))}
          </div>
        </MacroPanel>
      ) : null}
      <MacroPanel
        ariaLabel="利率数据源状态"
        className="macro-rates-source-diagnostics"
        meta={view.diagnostics.sourceMeta ?? "来源状态"}
        title="数据源状态"
      >
        <MacroSourceTable caption="利率数据源" source={module.provenance} />
      </MacroPanel>
    </div>
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
