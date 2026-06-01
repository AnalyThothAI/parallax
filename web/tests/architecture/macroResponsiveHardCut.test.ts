import { readdirSync, readFileSync, statSync } from "node:fs";
import { basename, join } from "node:path";

import { describe, expect, it } from "vitest";

const macroRoot = join(process.cwd(), "src/features/macro");

const collectCssFiles = (directory: string): string[] =>
  readdirSync(directory)
    .flatMap((entry) => {
      const path = join(directory, entry);
      const stats = statSync(path);

      if (stats.isDirectory()) {
        return collectCssFiles(path);
      }

      if (stats.isFile() && path.endsWith(".css") && !path.endsWith(".module.css")) {
        return [path];
      }

      return [];
    })
    .sort();

const stripBlockComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

const macroCssFiles = collectCssFiles(macroRoot);

const macroCss = () => macroCssFiles.map((file) => readFileSync(file, "utf8")).join("\n");

const strippedMacroCss = () => stripBlockComments(macroCss());

describe("macro responsive hard cut", () => {
  it("discovers macro side-effect CSS owners", () => {
    const discoveredFileNames = macroCssFiles.map((file) => basename(file));

    expect(macroCssFiles.length).toBeGreaterThan(0);
    expect(discoveredFileNames).toEqual(
      expect.arrayContaining([
        "macroCharts.css",
        "macroMetricStrip.css",
        "macroPageScaffold.css",
        "macroPanel.css",
        "macroPages.css",
        "macroRatesWorkbench.css",
        "macroShell.css",
        "macroTableFrame.css",
        "macroTables.css",
      ]),
    );
  });

  it("does not use destructive word wrapping in macro CSS", () => {
    const css = strippedMacroCss();

    expect(css).not.toMatch(/overflow-wrap\s*:\s*anywhere\b/);
    expect(css).not.toMatch(/word-break\s*:\s*break-all\b/);
  });

  it("does not keep retired macro layout selectors", () => {
    const css = strippedMacroCss();

    expect(css).not.toContain(".macro-page-panel-current");
    expect(css).not.toContain(".macro-correlation-head");
    expect(css).not.toContain(".macro-assets-index-matrix-wrap");
    expect(css).not.toContain(".macro-data-table-wrap");
    expect(css).not.toContain(".macro-page-kpi");
    expect(css).not.toContain(".macro-page-kpi-strip");
    expect(css).not.toContain(".macro-correlation-page");
    expect(css).not.toContain(".macro-source-table");
  });

  it("uses the frontend breakpoint and letter-spacing contract", () => {
    const css = strippedMacroCss();
    const mediaQueries = Array.from(css.matchAll(/@media\s+([^{]+)\{/g), ([, query]) =>
      query.replace(/\s+/g, " ").trim(),
    );
    const allowedMediaQueries = new Set([
      "(max-width: 767px)",
      "(min-width: 768px) and (max-width: 1279px)",
      "(min-width: 1280px)",
    ]);
    const offContractMediaQueries = mediaQueries.filter((query) => !allowedMediaQueries.has(query));
    const offContractLetterSpacing = Array.from(
      css.matchAll(/letter-spacing\s*:\s*([^;}]+)/g),
      ([match, value]) => ({ match, value: value.replace(/;$/, "").trim() }),
    )
      .filter(({ value }) => value !== "0")
      .map(({ match }) => match);

    expect(offContractMediaQueries).toEqual([]);
    expect(offContractLetterSpacing).toEqual([]);
    expect(css).not.toMatch(/font-size:\s*[^;}]*v(?:w|h|min|max)/);
  });
});
