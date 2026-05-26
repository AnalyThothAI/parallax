import type { MacroSemanticRecord } from "@lib/types";

import { formatMacroScalar } from "../../model/macroPageViewModel";
import { MacroPanel } from "./MacroPanel";

export function MacroReadPanel({
  ariaLabel = "模块判断",
  meta,
  read,
  summary,
  title = "模块判断",
}: {
  ariaLabel?: string;
  meta?: string | null;
  read: MacroSemanticRecord;
  summary: string;
  title?: string;
}) {
  const entries = READ_FIELDS.map((field) => ({
    key: field.key,
    label: field.label,
    value: read[field.key],
  })).filter((entry) => hasMacroValue(entry.value));

  return (
    <MacroPanel ariaLabel={ariaLabel} meta={meta} span="major" title={title}>
      <p className="macro-read-summary">{summary}</p>
      {entries.length > 0 ? (
        <div className="macro-read-list">
          {entries.map(({ key, label, value }) => (
            <div className="macro-read-row" key={key}>
              <span>{label}</span>
              <b>{formatMacroScalar(value)}</b>
            </div>
          ))}
        </div>
      ) : null}
    </MacroPanel>
  );
}

function hasMacroValue(value: unknown): boolean {
  if (typeof value === "number" || typeof value === "boolean") {
    return true;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  return Boolean(value && typeof value === "object" && Object.keys(value).length > 0);
}

const READ_FIELDS = [
  { key: "regime_label", label: "宏观状态" },
  { key: "regime", label: "宏观状态" },
  { key: "confidence_label", label: "规则覆盖" },
  { key: "crypto_read", label: "加密影响" },
  { key: "token_impact", label: "代币影响" },
  { key: "data_note", label: "数据说明" },
  { key: "methodology_note", label: "方法说明" },
] as const;
