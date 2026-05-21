import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");
const testRoot = join(webRoot, "tests");
const sourceExtensions = new Set([".ts", ".tsx"]);
const oldTokenImageProxyPattern = /\/api\/token-image(?!s)/;

describe("token image hard cut", () => {
  it("does not restore the old frontend URL compatibility helper", () => {
    expect(existsSync(join(srcRoot, "shared", "model", "tokenImageUrl.ts"))).toBe(false);

    const offenders = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return [
          text.includes("tokenImageUrl") ? `${relative(webRoot, path)}: tokenImageUrl` : null,
          oldTokenImageProxyPattern.test(text) ? `${relative(webRoot, path)}: /api/token-image` : null,
          text.includes("gmgn.ai/external-res") ? `${relative(webRoot, path)}: gmgn.ai/external-res` : null,
        ].filter((item): item is string => item !== null);
      });

    expect(offenders).toEqual([]);
  });

  it("keeps frontend tests from depending on the removed proxy helper", () => {
    const offenders = collectFiles(testRoot)
      .filter((path) => sourceExtensions.has(extname(path)) && !path.endsWith("tokenImageHardCut.test.ts"))
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return [
          text.includes("tokenImageUrl") ? `${relative(webRoot, path)}: tokenImageUrl` : null,
          oldTokenImageProxyPattern.test(text) ? `${relative(webRoot, path)}: /api/token-image` : null,
        ].filter((item): item is string => item !== null);
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
