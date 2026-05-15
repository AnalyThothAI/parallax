import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "../../src");
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
    const obsidianCss = readSource("shared/ui/obsidian.css");
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
      .filter((path) =>
        /^export\s+\{[^}]+Route[^}]+\}\s+from\s+/.test(readFileSync(path, "utf8").trim()),
      )
      .map((path) => relative(webRoot, path));

    expect(routeShells).toEqual([]);
  });

  it("keeps cockpit shell geometry centralized and route content scrollable", () => {
    const cockpitCss = readSource("features/cockpit/ui/cockpit.css");

    expect(cockpitCss).toContain("--cockpit-rail-width");
    expect(cockpitCss).toContain("--cockpit-topbar-height");
    expect(cockpitCss).not.toContain("grid-template-columns: 220px");
    expect(cockpitCss).toMatch(/\.center-column\s*{[^}]*overflow:\s*auto;/s);
  });

  it("does not keep dead timeline compatibility selectors after shared timeline reuse", () => {
    const forbidden = [
      /stage-tape/,
      /search-stage-rail/,
      /search-chart-/,
      /search-lightweight-chart/,
      /search-timeline-summary/,
      /(^|[^a-z-])legend-candle/,
      /(^|[^a-z-])legend-social/,
    ];
    const offenders = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => relative(srcRoot, path) !== "test/obsidianArchitectureCleanout.test.ts")
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return forbidden
          .filter((pattern) => pattern.test(text))
          .map((pattern) => `${relative(webRoot, path)}: ${pattern.source}`);
      });

    expect(offenders).toEqual([]);
  });

  it("removes legacy watchlist and notification routing shims", () => {
    expect(existsSync(join(srcRoot, "lib/watchlist.ts"))).toBe(false);

    const notificationsController = readSource(
      "features/notifications/useNotificationsController.ts",
    );
    expect(notificationsController).not.toContain("buildSignalLabUrl");
    expect(notificationsController).toContain("watchlistPath");
  });

  it("removes the old token-target feature and shared audit components", () => {
    const deletedFiles = [
      "features/token-target/index.ts",
      "features/token-target/api/useTokenTargetQueries.ts",
      "features/token-target/state/tokenTargetRouteState.ts",
      "features/token-target/ui/TokenTargetCaseSummary.tsx",
      "features/token-target/ui/TokenTargetPage.tsx",
      "features/token-target/ui/tokenTarget.css",
      "shared/ui/TokenSocialMarketTimeline.tsx",
      "shared/ui/TokenPostsPanel.tsx",
      "shared/ui/ScoreLedger.tsx",
    ].filter((path) => existsSync(join(srcRoot, path)));

    const deletedTests = [
      "component/features/token-target/ui/TokenTargetPage.routing.test.tsx",
      "unit/features/token-target/state/tokenTargetRouteState.test.ts",
      "component/shared/ui/ScoreLedger.test.tsx",
    ].filter((path) => existsSync(join(webRoot, "tests", path)));

    expect([...deletedFiles, ...deletedTests]).toEqual([]);
  });

  it("keeps token routes hard-cut to the token-case feature", () => {
    const tokenTargetRoute = readSource("routes/token-target.route.tsx");

    expect(tokenTargetRoute).toContain('from "@features/token-case"');
    expect(tokenTargetRoute).not.toContain("@features/token-target");
  });

  it("keeps Search token_result free of deleted layout stack selectors", () => {
    const forbiddenSelectors = [
      "search-content-grid",
      "search-primary-stack",
      "search-insight-stack",
    ];
    const offenders = collectFiles(srcRoot)
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => relative(srcRoot, path) !== "test/obsidianArchitectureCleanout.test.ts")
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return forbiddenSelectors
          .filter((selector) => text.includes(selector))
          .map((selector) => `${relative(webRoot, path)}: ${selector}`);
      });

    expect(offenders).toEqual([]);
  });

  it("removes the legacy selected sidecar and its drawer-only components", () => {
    const removedDrawerFiles = [
      "features/live/ui/AccountLane.tsx",
      "features/live/ui/EvidenceDetailDrawer.tsx",
      "features/live/ui/TokenDetailDrawer.tsx",
      "features/live/ui/TokenReplayFocus.tsx",
      "features/live/ui/TokenTimeline.tsx",
      "shared/ui/DetailDrawer.tsx",
    ].filter((path) => existsSync(join(srcRoot, path)));

    expect(removedDrawerFiles).toEqual([]);

    const cockpitShell = readSource("features/cockpit/ui/CockpitShell.tsx");
    expect(cockpitShell).not.toContain("detailPanel");
    expect(cockpitShell).not.toContain("detail-task-panel");

    const mobileTask = readSource("features/cockpit/model/mobileTask.ts");
    expect(mobileTask).not.toContain("detail");

    const drawerCss = collectFiles(srcRoot)
      .filter((path) => extname(path) === ".css")
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        const matches = [...text.matchAll(/\.detail-(?:task-panel|drawer|window-control)\b/g)];
        return matches.map((match) => `${relative(webRoot, path)}: ${match[0]}`);
      });

    expect(drawerCss).toEqual([]);
  });

  it("keeps old Radar scoring labels out of live UI copy", () => {
    const forbiddenLabels = ["Attention", "Proof", "Reach", "Entry"];
    const liveUiFiles = collectFiles(join(srcRoot, "features/live/ui"))
      .filter((path) => sourceExtensions.has(extname(path)))
      .filter((path) => !path.endsWith(".test.tsx"))
      .flatMap((path) => {
        const text = readFileSync(path, "utf8");
        return forbiddenLabels
          .filter((label) => text.includes(label))
          .map((label) => `${relative(webRoot, path)}: ${label}`);
      });

    expect(liveUiFiles).toEqual([]);
  });

  it("keeps Search token_result free of resolver candidate sidebar rendering", () => {
    const searchPage = readSource("features/search/ui/SearchIntelPage.tsx");
    const tokenPage = readSource("features/search/ui/SearchTokenIntelPage.tsx");

    expect(`${searchPage}\n${tokenPage}`).not.toContain("search-sidebar-candidates");
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
