import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const srcRoot = join(webRoot, "src");
const testsRoot = join(webRoot, "tests");
const cockpitUiRoot = join(srcRoot, "features/cockpit/ui");

const shellSelectors = [
  ".cockpit-shell",
  ".cockpit-grid",
  ".center-column",
  ".topbar",
  ".desktop-side-rail",
  ".mobile-route-nav",
] as const;

const oversizedSideEffectCss = new Set([
  "features/live/ui/live.css",
  "shared/ui/shared.css",
  "features/signal-lab/ui/signalLab.css",
  "features/cockpit/ui/cockpit.css",
  "features/news/news.css",
  "features/macro/macro.css",
  "features/search/ui/search.css",
  "features/ops/ui/ops.css",
  "shared/ui/obsidian.css",
  "features/watchlist/ui/watchlist.css",
]);

const unlayeredSideEffectCss = new Set([
  "styles/tailwind.css",
]);

describe("responsive CSS contract", () => {
  it("keeps live task navigation out of cockpit shell CSS", () => {
    const shellCss = cockpitShellCssUnits()
      .map((path) => {
        const relativePath = relativeToWeb(path);
        const contents = readFileSync(path, "utf8");

        return `\n/* @source ${relativePath} */\n${contents}`;
      })
      .join("\n");
    const forbiddenFragments = [
      ".live-task-nav",
      ".mobile-task-nav",
      ".mobile-task-radar",
      ".mobile-task-tape",
      ".mobile-task-lab",
      "[data-mobile-task-panel",
    ];
    const offenders = findRules(shellCss).flatMap((rule) =>
      forbiddenFragments
        .filter((fragment) => rule.selector.includes(fragment))
        .map(
          (fragment) =>
            `${sourceMarkerBefore(shellCss, rule.start)}:${lineNumberWithinSourceMarker(
              shellCss,
              rule.start,
            )} owns live task fragment ${fragment} via ${compactSelector(rule.selector)}`,
        ),
    );

    expect(offenders).toEqual([]);
  });

  it("keeps live mobile task visibility owned by live.css", () => {
    const liveCssPath = join(srcRoot, "features/live/ui/live.css");
    const liveCss = readFileSync(liveCssPath, "utf8");
    const lastMobileGrid = findMobileMediaBlocks(liveCss).reduce((lastIndex, block) => {
      const matchingRule = [...findRules(block.body)]
        .reverse()
        .find(
          (rule) =>
            selectorContains(rule.selector, ".live-task-nav") &&
            declarationValue(rule.body, "display") === "grid",
        );

      return matchingRule ? Math.max(lastIndex, block.start + matchingRule.start) : lastIndex;
    }, -1);

    expect(
      lastMobileGrid,
      "live.css must include a mobile .live-task-nav display:grid rule",
    ).not.toBe(-1);
  });

  it("keeps mobile LivePage from using overlay navigation or the desktop bottom-deck grid", () => {
    const liveCssPath = join(srcRoot, "features/live/ui/live.css");
    const liveCss = readFileSync(liveCssPath, "utf8");
    const mobileBlocks = findMobileMediaBlocks(liveCss);
    const livePageMobileRules = mobileBlocks.flatMap((block) =>
      findRules(block.body).filter((rule) => selectorContains(rule.selector, ".live-page")),
    );
    const radarPanelMobileRules = mobileBlocks.flatMap((block) =>
      findRules(block.body).filter((rule) => selectorContains(rule.selector, ".radar-panel")),
    );
    const liveTaskNavMobileRules = mobileBlocks.flatMap((block) =>
      findRules(block.body).filter((rule) => selectorContains(rule.selector, ".live-task-nav")),
    );

    expect(
      livePageMobileRules.some(
        (rule) =>
          declarationValue(rule.body, "grid-template-rows") === "minmax(0, 1fr) auto" &&
          declarationValue(rule.body, "overflow") === "hidden",
      ),
      "mobile .live-page must replace the desktop two-row bottom-deck grid with content + task-nav rows",
    ).toBe(true);
    expect(
      radarPanelMobileRules.some(
        (rule) =>
          declarationValue(rule.body, "grid-template-rows") === "auto minmax(0, 1fr)" &&
          declarationValue(rule.body, "overflow") === "hidden",
      ),
      "mobile .radar-panel must bound the token row scroller above the Live task nav",
    ).toBe(true);
    expect(
      liveTaskNavMobileRules.some((rule) => declarationValue(rule.body, "position") === "static"),
      "mobile .live-task-nav must be a real LivePage layout row instead of a fixed overlay",
    ).toBe(true);
  });

  it("keeps desktop-side-rail hidden in the mobile shell contract", () => {
    const matches = cockpitShellCssUnits().flatMap((path) => {
      const css = readFileSync(path, "utf8");

      return findMobileMediaBlocks(css).flatMap((block) =>
        findRules(block.body)
          .filter((rule) => selectorContains(rule.selector, ".desktop-side-rail"))
          .filter((rule) => declarationValue(rule.body, "display") === "none")
          .map(() => relativeToWeb(path)),
      );
    });

    expect(
      matches,
      ".desktop-side-rail must declare display:none inside a max-width: 767px mobile rule",
    ).not.toEqual([]);
  });

  it("prevents non-cockpit feature CSS from owning cockpit shell selectors", () => {
    const offenders = collectFiles(join(srcRoot, "features"))
      .filter(isCssFile)
      .filter((path) => !relative(srcRoot, path).startsWith("features/cockpit/"))
      .flatMap((path) => {
        const css = readFileSync(path, "utf8");

        return findRules(css).flatMap((rule) =>
          shellSelectors
            .filter((selector) => selectorContains(rule.selector, selector))
            .map(
              (selector) =>
                `${relativeToWeb(path)}:${lineNumber(css, rule.start)} owns ${selector} via ${compactSelector(
                  rule.selector,
                )}`,
            ),
        );
      });

    expect(offenders).toEqual([]);
  });

  it("keeps live task panel visibility hooks in live CSS only", () => {
    const forbiddenFragments = [
      "[data-mobile-task-panel",
      ".mobile-task-radar",
      ".mobile-task-tape",
      ".mobile-task-lab",
    ];
    const offenders = collectFiles(join(srcRoot, "features"))
      .filter(isCssFile)
      .filter((path) => relativeToSrc(path) !== "features/live/ui/live.css")
      .flatMap((path) => {
        const css = readFileSync(path, "utf8");

        return findRules(css).flatMap((rule) =>
          forbiddenFragments
            .filter((fragment) => rule.selector.includes(fragment))
            .map(
              (fragment) =>
                `${relativeToWeb(path)}:${lineNumber(css, rule.start)} owns ${fragment} via ${compactSelector(
                  rule.selector,
                )}`,
            ),
        );
      });

    expect(offenders).toEqual([]);
  });

  it("keeps final shell visibility breakpoints in the cockpit shell contract file only", () => {
    const allowedPath = "src/features/cockpit/ui/cockpitShellContract.css";
    const contractOwnedFragments = [
      ".desktop-side-rail",
      ".mobile-route-nav",
    ];
    const offenders = cockpitShellCssUnits()
      .filter((path) => relativeToWeb(path) !== allowedPath)
      .flatMap((path) => {
        const css = readFileSync(path, "utf8");

        return findRules(css).flatMap((rule) =>
          contractOwnedFragments
            .filter((fragment) => rule.selector.includes(fragment))
            .map(
              (fragment) =>
                `${relativeToWeb(path)}:${lineNumber(css, rule.start)} owns ${fragment} via ${compactSelector(
                  rule.selector,
                )}`,
            ),
        );
      });

    expect(offenders).toEqual([]);
  });

  it("removes the retired shell-level business control panel path", () => {
    const responsiveControlPanelOffenders = collectFiles(srcRoot)
      .filter((path) => [".css", ".ts", ".tsx"].includes(extname(path)))
      .filter((path) => readFileSync(path, "utf8").includes("responsive-control-panel"))
      .map(relativeToSrc);

    expect(
      responsiveControlPanelOffenders,
      [
        "Shell must not keep the retired responsive-control-panel compatibility path.",
        "Route-specific filters belong to their feature pages; the shell owns only navigation, frame, scroll, and notifications.",
      ].join("\n"),
    ).toEqual([]);

    const cockpitIndex = readFileSync(join(srcRoot, "features/cockpit/index.ts"), "utf8");
    const cockpitRadarControlOffenders = collectFiles(join(srcRoot, "features/cockpit"))
      .filter((path) => [".ts", ".tsx"].includes(extname(path)))
      .filter((path) => readFileSync(path, "utf8").includes("RadarControls"))
      .map(relativeToSrc);

    expect(cockpitIndex).not.toContain("RadarControls");
    expect(cockpitRadarControlOffenders).toEqual([]);
    expect(existsSync(join(cockpitUiRoot, "RadarControls.tsx"))).toBe(false);
  });

  it("reports side-effect CSS files above the 700-line budget", () => {
    const oversized = collectFiles(srcRoot)
      .filter(isSideEffectCssFile)
      .map((path) => ({
        path,
        lines: readFileSync(path, "utf8").split(/\r?\n/).length,
        relativePath: relativeToSrc(path),
      }))
      .filter(({ lines }) => lines > 700);

    const newOversized = oversized
      .filter(({ relativePath }) => !oversizedSideEffectCss.has(relativePath))
      .map(({ relativePath, lines }) => `${relativePath} has ${lines} lines`);

    expect(
      newOversized,
      [
        "Side-effect CSS files must stay at or below 700 lines.",
        "Allowlisted oversized files are temporary and must be reduced during the responsive CSS architecture hard-cut plan.",
        ...oversized.map(({ relativePath, lines }) => `- ${relativePath}: ${lines} lines`),
      ].join("\n"),
    ).toEqual([]);
  });

  it("keeps page.setViewportSize calls in responsive or explicit desktop-only specs", () => {
    const offenders = collectFiles(testsRoot)
      .filter((path) => extname(path) === ".ts")
      .filter((path) => readFileSync(path, "utf8").includes("page.setViewportSize"))
      .filter((path) => !isViewportSpecAllowed(path, readFileSync(path, "utf8")))
      .map(
        (path) =>
          `${relativeToWeb(path)} uses page.setViewportSize outside a responsive or desktop-only spec`,
      );

    expect(offenders).toEqual([]);
  });

  it("requires side-effect CSS layers unless the file is on the Task 4 migration allowlist", () => {
    const offenders = collectFiles(srcRoot)
      .filter(isSideEffectCssFile)
      .filter((path) => !hasAppLayerDeclaration(readFileSync(path, "utf8")))
      .filter((path) => !unlayeredSideEffectCss.has(relativeToSrc(path)))
      .map(
        (path) =>
          `${relativeToSrc(
            path,
          )} is unlayered. Task 4 must wrap new side-effect CSS in @layer app.features, @layer app.shell, or another explicit app layer; only the exact migration allowlist may remain unlayered.`,
      );

    expect(offenders).toEqual([]);
  });
});

function cockpitShellCssUnits(): string[] {
  return readdirSync(cockpitUiRoot)
    .map((entry) => join(cockpitUiRoot, entry))
    .filter((path) => statSync(path).isFile())
    .filter((path) => basename(path).endsWith(".css") || basename(path).endsWith(".module.css"))
    .sort();
}

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}

function isCssFile(path: string): boolean {
  return extname(path) === ".css";
}

function isSideEffectCssFile(path: string): boolean {
  return isCssFile(path) && !basename(path).endsWith(".module.css");
}

function relativeToWeb(path: string): string {
  return relative(webRoot, path);
}

function relativeToSrc(path: string): string {
  return relative(srcRoot, path);
}

type CssRule = {
  body: string;
  selector: string;
  start: number;
};

function findRules(css: string): CssRule[] {
  const rules: CssRule[] = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(css)) !== null) {
    const selector = match[1].trim();

    if (!selector || selector.startsWith("@")) {
      continue;
    }

    rules.push({
      selector,
      body: match[2],
      start: match.index,
    });
  }

  return rules;
}

function findMobileMediaBlocks(css: string): Array<{ body: string; start: number }> {
  const blocks: Array<{ body: string; start: number }> = [];
  const mediaPattern =
    /@media\s+[^{]*(?:\(\s*max-width:\s*767px\s*\)|\(\s*width\s*<=\s*767px\s*\))[^{]*\{/g;
  let match: RegExpExecArray | null;

  while ((match = mediaPattern.exec(css)) !== null) {
    const bodyStart = mediaPattern.lastIndex;
    const bodyEnd = findMatchingBrace(css, bodyStart - 1);

    if (bodyEnd !== -1) {
      blocks.push({ body: css.slice(bodyStart, bodyEnd), start: match.index });
      mediaPattern.lastIndex = bodyEnd + 1;
    }
  }

  return blocks;
}

function findMatchingBrace(input: string, openBraceIndex: number): number {
  let depth = 0;

  for (let index = openBraceIndex; index < input.length; index += 1) {
    if (input[index] === "{") {
      depth += 1;
    } else if (input[index] === "}") {
      depth -= 1;

      if (depth === 0) {
        return index;
      }
    }
  }

  return -1;
}

function selectorContains(selectorList: string, classSelector: string): boolean {
  const className = classSelector.slice(1).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-zA-Z0-9_-])\\.${className}(?![a-zA-Z0-9_-])`).test(selectorList);
}

function declarationValue(body: string, property: string): string | undefined {
  const declarationPattern = new RegExp(`${property}\\s*:\\s*([^;!}]+)`, "i");
  return body.match(declarationPattern)?.[1]?.trim().toLowerCase();
}

function compactSelector(selector: string): string {
  return selector.replace(/\s+/g, " ");
}

function lineNumber(input: string, index: number): number {
  return input.slice(0, index).split(/\r?\n/).length;
}

function sourceMarkerBefore(input: string, index: number): string {
  const markerMatches = [...input.slice(0, index).matchAll(/\/\* @source ([^*]+) \*\//g)];
  return markerMatches.at(-1)?.[1] ?? "unknown.css";
}

function lineNumberWithinSourceMarker(input: string, index: number): number {
  const markerMatches = [...input.slice(0, index).matchAll(/\/\* @source [^*]+ \*\//g)];
  const marker = markerMatches.at(-1);

  if (!marker) {
    return lineNumber(input, index);
  }

  return lineNumber(input.slice(marker.index ?? 0, index), index - (marker.index ?? 0)) - 1;
}

function isViewportSpecAllowed(path: string, contents: string): boolean {
  const relativePath = relativeToWeb(path);

  return (
    /(^|\/)(responsive|mobile|tablet|viewport)[^/]*\.spec\.ts$/.test(relativePath) ||
    /(^|\/)[^/]*(desktop-only|desktop)[^/]*\.spec\.ts$/.test(relativePath) ||
    contents.includes("@responsive-spec") ||
    contents.includes("@desktop-only-spec")
  );
}

function hasAppLayerDeclaration(css: string): boolean {
  return /@layer\s+app\.(base|primitives|shell|features|overrides)\b/.test(css);
}
