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
  narrative_not_supported_for_window: "admission unsupported",
  no_current_admission: "not admitted",
  out_of_frontier: "out of current frontier",
  suppressed: "suppressed",
  unsupported_window: "admission unsupported",
};
