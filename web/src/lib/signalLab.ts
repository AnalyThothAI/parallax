export function signalLabLabel(value: string | null | undefined): string {
  const text = value?.trim();
  if (!text) {
    return "-";
  }
  return text
    .replaceAll("harness_snapshot:", "signal_snapshot:")
    .replaceAll("social-harness", "signal-lab")
    .replaceAll("harness", "signal-lab");
}
