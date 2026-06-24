import { tableCaption, tableIdentifier } from "../../model/macroModulePageModel";
import type { RatesDetailTable } from "../../model/macroRatesWorkbenchModel";
import { MacroPanel } from "../primitives/MacroPanel";
import { MacroDataTable } from "../tables/MacroDataTable";

export function RatesDetailTables({ tables }: { tables: RatesDetailTable[] }) {
  const primaryTables = tables.filter(
    (entry) => entry.role === "primary" && renderableTable(entry.table),
  );

  if (primaryTables.length === 0) {
    return null;
  }

  return (
    <MacroPanel
      ariaLabel="利率明细"
      className="macro-rates-detail-tables macro-rates-detail-panel"
      meta={`${primaryTables.length} 张`}
      span="full"
      title="利率明细"
    >
      <div className="macro-rates-table-stack">
        {primaryTables.map(({ table }) => (
          <RatesDetailTableBlock key={String(table.id)} table={table} />
        ))}
      </div>
    </MacroPanel>
  );
}

function renderableTable(table: RatesDetailTable["table"]): boolean {
  return Boolean(tableIdentifier(table) && tableCaption(table) && (table.rows?.length ?? 0) > 0);
}

function RatesDetailTableBlock({ table }: { table: RatesDetailTable["table"] }) {
  const caption = tableCaption(table);
  return caption ? <MacroDataTable caption={caption} table={table} /> : null;
}
