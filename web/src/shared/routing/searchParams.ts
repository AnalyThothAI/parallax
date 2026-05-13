export function compactSearch(values: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    const normalized = String(value ?? "").trim();
    if (normalized) {
      params.set(key, normalized);
    }
  }
  return params.toString();
}

export function searchWithOptionalPrefix(params: URLSearchParams): string {
  const search = params.toString();
  return search ? `?${search}` : "";
}
