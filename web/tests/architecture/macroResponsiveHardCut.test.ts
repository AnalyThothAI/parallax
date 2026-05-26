import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const macroCssFiles = [
  "src/features/macro/ui/pages/macroPages.css",
  "src/features/macro/ui/primitives/macroMetricStrip.css",
  "src/features/macro/ui/primitives/macroPageScaffold.css",
  "src/features/macro/ui/primitives/macroPanel.css",
  "src/features/macro/ui/tables/macroTables.css",
  "src/features/macro/ui/tables/macroTableFrame.css",
  "src/features/macro/ui/shell/macroShell.css",
  "src/features/macro/ui/charts/macroCharts.css",
].map((path) => join(process.cwd(), path));

const macroCss = () =>
  macroCssFiles
    .filter((file) => existsSync(file))
    .map((file) => readFileSync(file, "utf8"))
    .join("\n");

describe("macro responsive hard cut", () => {
  it("does not use destructive word wrapping in macro CSS", () => {
    const css = macroCss();

    expect(css).not.toMatch(/overflow-wrap:\s*anywhere/);
    expect(css).not.toMatch(/word-break:\s*break-all/);
  });

  it("does not keep retired macro layout selectors", () => {
    const css = macroCss();

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
    const css = macroCss();
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
      css.matchAll(/letter-spacing:\s*([^;}]+)/g),
      ([match, value]) => ({ match, value: value.trim() }),
    )
      .filter(({ value }) => value !== "0")
      .map(({ match }) => match);

    expect(offContractMediaQueries).toEqual([]);
    expect(offContractLetterSpacing).toEqual([]);
    expect(css).not.toMatch(/font-size:\s*[^;}]*v(?:w|h|min|max)/);
  });
});
