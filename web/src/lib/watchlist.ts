import type { LivePayload } from "@lib/types";

export type WatchlistRow = {
  handle: string;
  unreadCount: number;
  lastSeenAtMs: number | null;
};

type BuildWatchlistRowsInput = {
  handles: string[];
  accountUnreadCounts?: Record<string, number> | null;
  liveItems: LivePayload[];
};

export function buildWatchlistRows({
  handles,
  accountUnreadCounts,
  liveItems,
}: BuildWatchlistRowsInput): WatchlistRow[] {
  const normalizedHandles = dedupeHandles(handles);
  const latestByHandle = new Map<string, number>();
  for (const item of liveItems) {
    const handle = eventHandle(item)?.toLowerCase();
    const receivedAtMs = Number(item.event.received_at_ms ?? 0);
    if (!handle || !receivedAtMs) {
      continue;
    }
    latestByHandle.set(handle, Math.max(latestByHandle.get(handle) ?? 0, receivedAtMs));
  }
  const originalIndex = new Map(normalizedHandles.map((handle, index) => [handle, index]));
  return normalizedHandles
    .map((handle) => ({
      handle,
      unreadCount: Number(accountUnreadCounts?.[handle] ?? 0),
      lastSeenAtMs: latestByHandle.get(handle) ?? null,
    }))
    .sort(
      (a, b) =>
        b.unreadCount - a.unreadCount ||
        Number(b.lastSeenAtMs ?? 0) - Number(a.lastSeenAtMs ?? 0) ||
        Number(originalIndex.get(a.handle) ?? 0) - Number(originalIndex.get(b.handle) ?? 0),
    );
}

function dedupeHandles(handles: string[]): string[] {
  const seen = new Set<string>();
  const rows: string[] = [];
  for (const raw of handles) {
    const handle = raw.trim().replace(/^@/, "").toLowerCase();
    if (!handle || seen.has(handle)) {
      continue;
    }
    seen.add(handle);
    rows.push(handle);
  }
  return rows;
}

function eventHandle(item: LivePayload): string | null {
  if (item.event.author_handle) {
    return item.event.author_handle;
  }
  return item.event.author?.handle ?? null;
}
