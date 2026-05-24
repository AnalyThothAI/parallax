import type { MacroModuleTable, MacroSemanticRecord } from "@lib/types";

import { emptyTable, tableCaption, tableIdentifier } from "../../model/macroModulePageModel";
import { macroRouteLabel } from "../../model/macroRoutes";
import { MacroDataTable } from "../tables/MacroDataTable";
import { MacroSourceTable } from "../tables/MacroSourceTable";

import { MacroModulePageFrame, type MacroModulePageProps } from "./MacroModulePageFrame";

export function MacroCryptoDerivativesPage(props: MacroModulePageProps) {
  const cexTable =
    props.module.tables.find((table) => tableIdentifier(table) === "cex_perp_board") ??
    emptyTable("cex_perp_board");
  const frameModule = {
    ...props.module,
    tables: props.module.tables.filter((table) => tableIdentifier(table) !== "cex_perp_board"),
  };
  return (
    <div className="macro-crypto-derivatives-page">
      <MacroModulePageFrame
        {...props}
        module={frameModule}
        pageLabel={macroRouteLabel(props.moduleId)}
        showSupportingTable={false}
      />
      <section className="macro-page-panel macro-page-panel-derivatives" aria-label="CEX 永续看板">
        <MacroDataTable caption={tableCaption(cexTable)} table={cexTable} />
      </section>
      <section className="macro-page-panel" aria-label="CEX 数据源">
        <MacroSourceTable caption="CEX 数据源" source={tableSource(cexTable)} />
      </section>
    </div>
  );
}

function tableSource(table: MacroModuleTable): MacroSemanticRecord {
  if (table.source && typeof table.source === "object") {
    return { rows: [table.source as MacroSemanticRecord] };
  }
  return { rows: [{ source_label: "CEX OI Radar", status: table.status ?? "missing" }] };
}
