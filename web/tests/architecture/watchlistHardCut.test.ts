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
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
