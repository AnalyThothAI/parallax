import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const webRoot = join(srcRoot, "..");

const legacyTokenNames = [
  "bg",
  "panel",
  "panel-2",
  "panel-3",
  "text",
  "ink",
  "muted",
  "faint",
  "accent",
  "accent-soft",
  "accent-line",
  "green",
  "red",
  "blue",
  "danger-soft",
];

const sourceExtensions = new Set([".css", ".ts", ".tsx"]);

describe("Obsidian Desk architecture cleanout", () => {
  it("keeps design tokens to Obsidian semantics without compatibility aliases", () => {
    const tokens = readSource("styles/tokens.css");
    const forbiddenDefinitions = [
      ...legacyTokenNames.map((name) => `--${name}:`),
      "--case-",
    ].filter((needle) => tokens.includes(needle));

    expect(forbiddenDefinitions).toEqual([]);
  });

  it("does not consume legacy or case mirror CSS variables", () => {
    const offenders = collectFiles(srcRoot)
      .filter((path) => extname(path) === ".css")
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        const matches = [
          ...text.matchAll(
            /var\(--(?:bg|panel|panel-2|panel-3|text|ink|muted|faint|accent|accent-soft|accent-line|green|red|blue|danger-soft|case-[^)]+)\)/g,
          ),
        ];
        return matches.map((match) => `${relative(webRoot, path)}: ${match[0]}`);
      });

    expect(offenders).toEqual([]);
  });

  it("keeps Obsidian component tone colors behind tokens", () => {
    const obsidianCss = readSource("shared/ui/obsidian.module.css");
    const hardCodedToneColors = [...obsidianCss.matchAll(/#[0-9a-fA-F]{6}/g)].map(
      (match) => match[0],
    );

    expect(hardCodedToneColors).toEqual([]);
  });

  it("uses a real shared case-file primitive package instead of the old obsidian barrel", () => {
    expect(existsSync(join(srcRoot, "shared/ui/case-file/index.ts"))).toBe(true);

    const oldBarrelConsumers = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => !relative(srcRoot, path).startsWith("test/"))
      .filter((path) => /@shared\/ui\/obsidian["']/.test(readFileSync(path, "utf8")))
      .map((path) => relative(webRoot, path));

    expect(oldBarrelConsumers).toEqual([]);
  });

  it("keeps route ownership in route modules, not CockpitApp", () => {
    const cockpitApp = readSource("app/CockpitApp.tsx");
    expect(cockpitApp).not.toMatch(/<Routes?\b/);

    const routeShells = collectFiles(join(srcRoot, "routes"))
      .filter((path) => extname(path) === ".tsx")
      .filter((path) => /^export\s+\{[^}]+Route[^}]+\}\s+from\s+/.test(readFileSync(path, "utf8").trim()))
      .map((path) => relative(webRoot, path));

    expect(routeShells).toEqual([]);
  });

  it("removes legacy watchlist and notification routing shims", () => {
    expect(existsSync(join(srcRoot, "lib/watchlist.ts"))).toBe(false);

    const notificationsController = readSource("features/notifications/useNotificationsController.ts");
    expect(notificationsController).not.toContain("buildSignalLabUrl");
    expect(notificationsController).toContain("watchlistPath");
  });

  it("keeps token-target independent from live feature internals", () => {
    const tokenTargetFiles = collectFiles(join(srcRoot, "features/token-target"))
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => !relative(srcRoot, path).startsWith("features/token-target/ui/__tests__"))
      .filter((path) => readFileSync(path, "utf8").includes("@features/live"))
      .map((path) => relative(webRoot, path));

    expect(tokenTargetFiles).toEqual([]);
  });
});

function readSource(path: string): string {
  return readFileSync(join(srcRoot, path), "utf8");
}

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    const stats = statSync(path);
    if (stats.isDirectory()) {
      return collectFiles(path);
    }
    return [path];
  });
}
