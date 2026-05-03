import type { EventRecord, TokenFlowItem } from "../api/types";

export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  const abs = Math.abs(value);
  if (abs >= 1_000_000) {
    return `${trim(value / 1_000_000)}M`;
  }
  if (abs >= 1_000) {
    return `${trim(value / 1_000)}K`;
  }
  return String(Math.round(value));
}

export function formatRelativeTime(value: number | null | undefined, now = Date.now()): string {
  if (!value) {
    return "-";
  }
  const delta = Math.max(0, now - value);
  if (delta < 60_000) {
    return `${Math.floor(delta / 1000)}s`;
  }
  if (delta < 3_600_000) {
    return `${Math.floor(delta / 60_000)}m`;
  }
  if (delta < 86_400_000) {
    return `${Math.floor(delta / 3_600_000)}h`;
  }
  return `${Math.floor(delta / 86_400_000)}d`;
}

export function formatPercentShare(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  const percent = Math.max(0, value) * 100;
  return percent >= 10 ? `${Math.round(percent)}%` : `${percent.toFixed(1).replace(/\.0$/, "")}%`;
}

export function eventHandle(event: EventRecord): string {
  return (event.author_handle ?? event.author?.handle ?? "unknown").replace(/^@/, "").toLowerCase();
}

export function eventText(event: EventRecord): string {
  return event.text_clean ?? event.content?.text ?? event.search_text ?? "";
}

export function tokenLabel(item: TokenFlowItem): string {
  if (item.entity_type === "symbol") {
    return `$${item.normalized_value}`;
  }
  const value = item.normalized_value;
  return value.length > 18 ? `${value.slice(0, 8)}...${value.slice(-6)}` : value;
}

function trim(value: number): string {
  return value.toFixed(value >= 10 ? 0 : 1).replace(/\.0$/, "");
}
