import { eventText, formatRelativeTime } from "@lib/format";
import type { LivePayload } from "@lib/types";
import type { WatchlistRow } from "@lib/watchlist";
import { searchPath } from "@shared/routing/paths";

export type WatchlistEvidence = {
  body: string;
  href?: string;
  id: string;
  meta: string;
  title: string;
};

export type WatchlistCluster = {
  count: number;
  label: string;
  query: string;
};

export type WatchlistSearchLink = {
  href: string;
  label: string;
};

export type WatchlistAccountCase = {
  emptyState: string | null;
  handle: string;
  lastSeenAtMs: number | null;
  narrativeClusters: WatchlistCluster[];
  recentEvents: WatchlistEvidence[];
  riskNotes: string[];
  searchLinks: WatchlistSearchLink[];
  tokenMentions: WatchlistCluster[];
  unreadCount: number;
};

type BuildWatchlistAccountCasesInput = {
  liveItems: LivePayload[];
  rows: WatchlistRow[];
};

export function buildWatchlistAccountCases({
  liveItems,
  rows,
}: BuildWatchlistAccountCasesInput): WatchlistAccountCase[] {
  return rows.map((row) => {
    const handle = normalizeWatchlistHandle(row.handle) ?? row.handle.toLowerCase();
    const accountEvents = liveItems
      .filter((item) => normalizeWatchlistHandle(eventHandle(item)) === handle)
      .sort(
        (left, right) =>
          Number(right.event.received_at_ms ?? 0) - Number(left.event.received_at_ms ?? 0),
      );
    const recentEvents = accountEvents.slice(0, 8).map((item) => ({
      body: eventText(item.event) || "No text captured for this event.",
      href: item.event.canonical_url ?? undefined,
      id: item.event.event_id,
      meta: item.event.received_at_ms
        ? `${formatRelativeTime(item.event.received_at_ms)} ago`
        : "no timestamp",
      title: `@${handle}`,
    }));
    const tokenMentions = countClusters(accountEvents.flatMap(tokenQueries));
    const narrativeClusters = countClusters(accountEvents.flatMap(narrativeQueries));

    return {
      emptyState: recentEvents.length ? null : "No source events in this window.",
      handle,
      lastSeenAtMs: row.lastSeenAtMs,
      narrativeClusters,
      recentEvents,
      riskNotes: accountEvents.some((item) => !eventText(item.event))
        ? ["Some events have no captured text."]
        : [],
      searchLinks: [
        {
          href: searchPath({ q: `@${handle}` }),
          label: "Search account",
        },
      ],
      tokenMentions,
      unreadCount: row.unreadCount,
    };
  });
}

export function normalizeWatchlistHandle(value?: string | null): string | null {
  const handle = value?.trim().replace(/^@+/, "").toLowerCase();
  return handle ? handle : null;
}

function eventHandle(item: LivePayload): string | null {
  return item.event.author_handle ?? item.event.author?.handle ?? null;
}

function tokenQueries(item: LivePayload): string[] {
  const fromEvent = item.event.cashtags ?? [];
  const fromEntities = item.entities
    .filter((entity) => entity.entity_type === "symbol" || entity.entity_type === "cashtag")
    .map((entity) => entity.normalized_value);
  const fromIntents = item.token_intents?.map((intent) => intent.display_symbol ?? "") ?? [];
  return [
    ...new Set(
      [...fromEvent, ...fromEntities, ...fromIntents]
        .map((value) => value.trim().replace(/^\$+/, "").toUpperCase())
        .filter(Boolean)
        .map((value) => `$${value}`),
    ),
  ];
}

function narrativeQueries(item: LivePayload): string[] {
  return (item.event.hashtags ?? [])
    .map((value) => value.trim().replace(/^#+/, "").toLowerCase())
    .filter(Boolean)
    .map((value) => `#${value}`);
}

function countClusters(values: string[]): WatchlistCluster[] {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ count, label, query: label }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}
