export function normalizeWatchlistHandle(value?: string | null): string | null {
  const handle = value?.trim().replace(/^@+/, "").toLowerCase();
  return handle ? handle : null;
}
