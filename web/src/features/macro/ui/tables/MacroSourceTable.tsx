import type { MacroSemanticRecord } from "@lib/types";

import { MacroDataTable } from "./MacroDataTable";

export function MacroSourceTable({
  caption,
  source,
}: {
  caption: string;
  source: MacroSemanticRecord;
}) {
  const entries = Object.entries(source);
  if (entries.length === 0) {
    return (
      <div aria-label={`${caption}空状态`} className="macro-table-state-panel" role="status">
        暂无数据源元信息
      </div>
    );
  }
  return (
    <MacroDataTable
      caption={caption}
      table={{ table_id: "source_metadata", rows: entries.map(sourceRow) }}
    />
  );
}

function sourceRow([field, value]: [string, unknown]): MacroSemanticRecord {
  return { field, value };
}
