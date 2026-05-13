import type { SearchItem } from "@lib/types";

export type SearchTopicBucket = {
  posts: number;
  startMs: number;
};

const TOPIC_BUCKET_MS = 60 * 60 * 1000;

export function buildTopicBuckets(items: SearchItem[]): SearchTopicBucket[] {
  const times = items
    .map((item) => item.event.received_at_ms)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!times.length) {
    return [{ posts: 0, startMs: 0 }];
  }
  const min = Math.min(...times);
  const grouped = new Map<number, number>();
  for (const time of times) {
    const startMs = min + Math.floor((time - min) / TOPIC_BUCKET_MS) * TOPIC_BUCKET_MS;
    grouped.set(startMs, (grouped.get(startMs) ?? 0) + 1);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([startMs, posts]) => ({ posts, startMs }));
}
