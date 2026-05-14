import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");

describe("CSS ownership", () => {
  it("keeps main.tsx free of feature CSS retention", () => {
    const main = readFileSync(join(srcRoot, "main.tsx"), "utf8");

    expect(main).not.toContain("moduleKeep");
    expect(main).not.toContain("document.documentElement.classList.add");
    expect(main).not.toMatch(/features\/.+\.module\.css/);
    expect(main).not.toMatch(/shared\/ui\/.+\.module\.css/);
  });

  it("does not define moduleKeep classes", () => {
    const offenders = collectFiles(srcRoot)
      .filter((path) => extname(path) === ".css")
      .filter((path) => readFileSync(path, "utf8").includes("moduleKeep"))
      .map((path) => relative(webRoot, path));

    expect(offenders).toEqual([]);
  });
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
