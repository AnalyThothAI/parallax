import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");
const allowedTabsWrapper = "src/shared/ui/tabs.tsx";
const sourceExtensions = new Set([".ts", ".tsx"]);

describe("shared primitive imports", () => {
  it("flags direct Radix Tabs package imports outside the shared wrapper", () => {
    expect(
      disallowedTabsImportMessages(
        "src/features/news/BadTabsImport.tsx",
        'import * as Tabs from "@radix-ui/react-tabs";',
      ),
    ).toEqual([
      'src/features/news/BadTabsImport.tsx: import * as Tabs from "@radix-ui/react-tabs"',
    ]);
  });

  it("flags named Tabs imports from aggregate Radix outside the shared wrapper", () => {
    expect(
      disallowedTabsImportMessages(
        "src/features/news/BadTabsImport.tsx",
        'import { Tabs as RadixTabs } from "radix-ui";',
      ),
    ).toEqual([
      'src/features/news/BadTabsImport.tsx: import { Tabs as RadixTabs } from "radix-ui"',
    ]);
  });

  it("routes Radix Tabs usage through the shared tabs primitive", () => {
    const offenders = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .flatMap((path) => {
        const relativePath = relative(webRoot, path);

        if (relativePath === allowedTabsWrapper) {
          return [];
        }

        return disallowedTabsImportMessages(relativePath, readFileSync(path, "utf8"));
      });

    expect(offenders).toEqual([]);
  });
});

function disallowedTabsImportMessages(relativePath: string, text: string): string[] {
  const importDeclarations = [
    ...text.matchAll(/import\s+(?:type\s+)?([\s\S]*?)\s+from\s+["']([^"']+)["']/g),
  ];

  return importDeclarations.flatMap((match) => {
    const [, importClause, source] = match;
    const importText = match[0].replace(/\s+/g, " ");

    if (source === "@radix-ui/react-tabs") {
      return [`${relativePath}: ${importText}`];
    }

    if (source !== "radix-ui") {
      return [];
    }

    if (!importsNamedTabs(importClause)) {
      return [];
    }

    return [`${relativePath}: ${importText}`];
  });
}

function importsNamedTabs(importClause: string): boolean {
  const namedBlock = importClause.match(/\{([\s\S]*?)\}/);

  if (!namedBlock) {
    return false;
  }

  return namedBlock[1]
    .split(",")
    .map((specifier) =>
      specifier
        .trim()
        .split(/\s+as\s+/i)[0]
        ?.trim(),
    )
    .includes("Tabs");
}

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
