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
  const cleaned = value.trim().replaceAll("_", " ");
  return cleaned ? cleaned : null;
}
