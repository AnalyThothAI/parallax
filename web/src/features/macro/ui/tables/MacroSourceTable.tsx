import type { MacroSemanticRecord } from "@lib/types";

import { MacroDataTable } from "./MacroDataTable";

export function MacroSourceTable({
  caption,
  source,
}: {
  caption: string;
  source: MacroSemanticRecord;
}) {
  const rows = sourceRows(source);
  if (rows.length === 0) {
    return (
      <div aria-label={`${caption}空状态`} className="macro-table-state-panel" role="status">
        暂无数据源元信息
      </div>
    );
  }
  return (
    <MacroDataTable
      caption={caption}
      table={{
        id: "source_metadata",
        columns: [
          { key: "source", label: "来源" },
          { key: "latest", label: "最新观测" },
          { key: "quality", label: "新鲜度/质量/状态" },
          { key: "count", label: "指标数" },
          { key: "participation", label: "计分" },
          { key: "notes", label: "备注" },
        ],
        rows,
      }}
    />
  );
}

function sourceRows(source: MacroSemanticRecord): MacroSemanticRecord[] {
  const rows = Array.isArray(source.rows) ? source.rows : [];
  return rows
    .map((row, index) => (isRecord(row) ? sourceRow(row, index) : null))
    .filter((row): row is MacroSemanticRecord => Boolean(row));
}

function sourceRow(row: MacroSemanticRecord, index: number): MacroSemanticRecord {
  const source = sourceLabel(row);
  const quality = qualityLabel(row);
  const latest = stringValue(row.latest_observed_at) ?? observedAtLabel(row.observed_at_ms) ?? "暂无";
  const count = numberValue(row.concept_count);
  const participation = scoreParticipationLabel(row.score_participation);
  const notes = notesLabel(row);
  return {
    row_id: `${source}:${index}`,
    cells: {
      source: { display_value: source, sort_value: source },
      latest: { display_value: latest, sort_value: latest },
      quality: { display_value: quality, sort_value: quality },
      count: { display_value: count === null ? "暂无" : String(count), sort_value: count },
      participation: { display_value: participation, sort_value: participation },
      notes: { display_value: notes, sort_value: notes },
    },
  };
}

function sourceLabel(row: MacroSemanticRecord): string {
  const raw =
    stringValue(row.source_label) ??
    stringValue(row.label) ??
    stringValue(row.source) ??
    stringValue(row.name);
  return displayText(raw, "数据源");
}

function statusLabel(row: MacroSemanticRecord): string {
  const label = stringValue(row.status_label);
  if (label) {
    return label;
  }
  const status = stringValue(row.status);
  return status ? STATUS_LABELS[status] ?? "未知状态" : "未知";
}

function qualityLabel(row: MacroSemanticRecord): string {
  const freshness = stringValue(row.freshness_label);
  const quality = stringValue(row.quality_label);
  const status = statusLabel(row);
  return [freshness, quality, status].filter(Boolean).join(" / ") || "未知";
}

function scoreParticipationLabel(value: unknown): string {
  if (value === true) {
    return "参与计分";
  }
  if (value === false) {
    return "计分排除";
  }
  return "暂无";
}

function notesLabel(row: MacroSemanticRecord): string {
  const notes = stringValue(row.notes) ?? stringValue(row.message);
  if (notes) {
    return displayText(notes, "存在降级原因");
  }
  const degradedReasons = Array.isArray(row.degraded_reasons) ? row.degraded_reasons : [];
  const labels = degradedReasons
    .map((reason) => (typeof reason === "string" ? displayText(reason, "存在降级原因") : null))
    .filter((reason): reason is string => Boolean(reason));
  return labels.join(", ") || "暂无";
}

function observedAtLabel(value: unknown): string | null {
  const timestamp = numberValue(value);
  if (timestamp === null) {
    return null;
  }
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

function isRecord(value: unknown): value is MacroSemanticRecord {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function displayText(value: string | null, fallback: string): string {
  if (!value) {
    return fallback;
  }
  return SOURCE_LABELS[value] ?? (looksInternalCode(value) ? fallback : value);
}

function looksInternalCode(value: string): boolean {
  return /^[a-z][a-z0-9_:.-]*$/.test(value);
}

const SOURCE_LABELS: Record<string, string> = {
  cex_market_intel: "CEX OI Radar",
  cex_oi_radar_board: "CEX OI Radar",
  coinglass: "Coinglass",
  fred: "FRED",
  nyfed: "NY Fed",
  yahoo: "Yahoo",
};

const STATUS_LABELS: Record<string, string> = {
  degraded: "降级",
  missing: "缺失",
  ok: "可用",
  partial: "部分可用",
  success: "可用",
  unavailable: "不可用",
};
