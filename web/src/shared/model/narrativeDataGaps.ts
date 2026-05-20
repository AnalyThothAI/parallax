export type NarrativeDataGap =
  | string
  | {
      code?: string | null;
      message?: string | null;
      reason?: string | null;
      [key: string]: unknown;
    }
  | null
  | undefined;

export function narrativeGapLabel(gap: NarrativeDataGap): string | null {
  if (typeof gap === "string") {
    return cleanGap(gap);
  }
  if (!gap || typeof gap !== "object") {
    return null;
  }
  return cleanGap(gap.message) ?? cleanGap(gap.reason) ?? cleanGap(gap.code);
}

export function narrativeGapLabels(gaps: NarrativeDataGap[] | null | undefined): string[] {
  return (gaps ?? [])
    .map((gap) => narrativeGapLabel(gap))
    .filter((gap): gap is string => Boolean(gap));
}

function cleanGap(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const reason = value.trim();
  const translated = REASON_LABELS[reason];
  if (translated) {
    return translated;
  }
  const cleaned = reason.replaceAll("_", " ");
  return cleaned ? cleaned : null;
}

const REASON_LABELS: Record<string, string> = {
  digest_updating: "叙事更新中",
  low_independent_author_count: "独立作者不足",
  low_semantic_coverage: "语义覆盖不足",
  low_source_volume: "叙事样本不足",
  material_delta_due: "叙事刷新排队中",
  narrative_not_supported_for_window: "5m 实时信号",
  no_ready_digest: "叙事待生成",
  out_of_frontier: "不在当前雷达前沿",
  not_in_current_frontier: "不在当前雷达前沿",
  semantic_labeling_pending: "叙事分析中",
  unsupported_window: "5m 实时信号",
};
