import { tableCaption } from "../../model/macroModulePageModel";
import type { RatesDetailTable } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroDataTable } from "../tables/MacroDataTable";

export function RatesDetailTables({ tables }: { tables: RatesDetailTable[] }) {
  const primaryTables = tables.filter(
    (entry) => entry.role === "primary" && (entry.table.rows?.length ?? 0) > 0,
  );

  return (
    <MacroPanel
      ariaLabel="利率明细"
      className="macro-rates-detail-tables macro-rates-detail-panel"
      meta={`${primaryTables.length} 张`}
      span="full"
      title="利率明细"
    >
      {primaryTables.length > 0 ? (
        <div className="macro-rates-table-stack">
          {primaryTables.map(({ table }) => (
            <MacroDataTable
              caption={tableCaption(table)}
              key={String(table.id ?? tableCaption(table))}
              table={table}
            />
          ))}
        </div>
      ) : (
        <div className="macro-rates-empty macro-rates-empty-compact" role="status">
          暂无利率明细
        </div>
      )}
    </MacroPanel>
  );
}
