import type { MacroSemanticRecord } from "@lib/types";

import { MacroHeatmap } from "../charts/MacroHeatmap";

export function MacroCorrelationMatrix({
  caption,
  rows,
}: {
  caption: string;
  rows: MacroSemanticRecord[];
}) {
  return <MacroHeatmap caption={caption} rows={rows} />;
}
