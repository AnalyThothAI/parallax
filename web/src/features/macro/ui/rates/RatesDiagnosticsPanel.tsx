import type { MacroModuleView } from "@lib/types";

import { tableCaption } from "../../model/macroModulePageModel";
import type { MacroDataHealthBucket } from "../../model/macroModulePresentation";
import type { RatesWorkbenchView } from "../../model/macroRatesWorkbenchModel";
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
    <MacroPanel
      ariaLabel="数据诊断"
      className="macro-rates-diagnostics-panel"
      meta={meta}
      span="full"
      title="数据诊断"
    >
      <div className="macro-rates-diagnostics-board">
        <div className="macro-rates-health-buckets">
          {buckets.map((bucket) => (
            <section className="macro-rates-health-bucket" key={bucket.key}>
              <div className="macro-rates-health-head">
                <h4>{bucket.label}</h4>
                <span>{bucket.referenceCount ?? bucket.items.length}</span>
              </div>
              {bucket.referenceCount ? (
                <p className="macro-rates-empty macro-rates-empty-compact">总览级缺口，仅供参考</p>
              ) : bucket.items.length > 0 ? (
                <div className="macro-rates-health-chip-list">
                  {bucket.items.map((item, index) => (
                    <span
                      className="macro-rates-health-chip"
                      key={`${bucket.key}:${item}:${index}`}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="macro-rates-empty macro-rates-empty-compact">暂无</p>
              )}
            </section>
          ))}
        </div>
        {diagnosticTables.length > 0 ? (
          <div className="macro-rates-table-stack">
            {diagnosticTables.map(({ table }) => (
              <MacroDataTable
                caption={tableCaption(table)}
                key={String(table.id ?? tableCaption(table))}
                table={table}
              />
            ))}
          </div>
        ) : null}
        <div className="macro-rates-source-diagnostics">
          <div className="macro-rates-health-head">
            <h4>来源状态</h4>
            <span>{view.diagnostics.sourceMeta ?? "来源状态"}</span>
          </div>
          <MacroSourceTable caption="利率数据源" source={module.provenance} />
        </div>
      </div>
    </MacroPanel>
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
