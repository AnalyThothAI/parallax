import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";

import { emptyTable, tableCaption } from "../../model/macroModulePageModel";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroCryptoDerivativesPage(props: MacroModulePageProps) {
  const cexTable =
    props.module.tables.find((table) => table.table_id === "cex_perp_board") ??
    emptyTable("cex_perp_board");
  const frameModule = {
    ...props.module,
    tables: props.module.tables.filter((table) => table.table_id !== "cex_perp_board"),
  };
  return (
    <div className="macro-crypto-derivatives-page">
      <MacroModulePageFrame
        {...props}
        module={frameModule}
        pageLabel="Crypto Derivatives"
        showSupportingTable={false}
      />
      <section className="macro-page-panel macro-page-panel-derivatives" aria-label="CEX perp board">
        <MacroDataTable caption={tableCaption(cexTable)} table={cexTable} />
      </section>
      <section className="macro-page-panel" aria-label="CEX source">
        <MacroSourceTable caption="CEX source" source={tableSource(cexTable)} />
      </section>
    </div>
  );
}

function tableSource(table: MacroModuleTable): MacroSemanticRecord {
  return table.source && typeof table.source === "object"
    ? (table.source as MacroSemanticRecord)
    : { status: table.status ?? "missing" };
}
