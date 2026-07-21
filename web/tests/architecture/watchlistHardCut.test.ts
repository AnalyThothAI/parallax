import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { describe, expect, it } from "vitest";

const srcRoot = join(process.cwd(), "src");
const sourceExtensions = new Set([".ts", ".tsx"]);

describe("watchlist hard cut", () => {
  it("does not restore selected-page live-buffer account cases", () => {
    const blocked = [
      "WatchlistAccountCase",
      "buildWatchlistAccountCases",
      "accountCases=",
      'searchParams.get("scope") as WatchlistTimelineScope',
      "WatchlistTimelineScope",
      "timeline_scope",
      "recent_signal_event_count",
      "total_signal_event_count",
      "signal_event_count",
      "watchlist-scope-tabs",
      "WatchlistSocialEvent",
    ];
    const offenders = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return blocked
          .filter((pattern) => text.includes(pattern))
          .map((pattern) => `${relative(srcRoot, path)}: ${pattern}`);
      });

    expect(offenders).toEqual([]);
  });

  it("keeps producer-owned overview and timeline fields required", () => {
    const contracts = readFileSync(join(srcRoot, "lib/types/frontend-contracts.ts"), "utf8");
    const watchlistContracts = contracts.slice(
      contracts.indexOf("export type WatchlistHandleRowOverview"),
      contracts.indexOf("export type SearchItem"),
    );
    const requiredFields = [
      "last_source_event_at_ms: number | null;",
      "recent_source_event_count: number;",
      "count: number;",
      "symbol: string | null;",
      "target_id: string | null;",
      "target_type: string | null;",
      "clusters_truncated: boolean;",
      "author_handle: string | null;",
      "action: string | null;",
      "text_clean: string | null;",
      "canonical_url: string | null;",
      "cashtags: string[];",
      "hashtags: string[];",
      "mentions: string[];",
      "event: EventRecord;",
      "token_resolutions: TokenResolutionRecord[];",
      "next_cursor: string | null;",
    ];

    for (const field of requiredFields) {
      expect(watchlistContracts).toContain(field);
    }
    expect(watchlistContracts).not.toContain("?:");
  });
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
