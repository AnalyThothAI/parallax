import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const macroRoot = join(webRoot, "src/features/macro");
const srcRoot = join(webRoot, "src");

const pageFiles = [
  "MacroOverviewPage.tsx",
  "MacroCrossAssetPage.tsx",
  "MacroRatesInflationPage.tsx",
  "MacroGrowthLaborPage.tsx",
  "MacroLiquidityFundingPage.tsx",
  "MacroCreditPage.tsx",
];

describe("macro decision workbench hard cut", () => {
  it("owns exactly six explicit pages without a registry or universal renderer", () => {
    const files = collectFiles(macroRoot);
    const actualPages = files
      .filter((path) => path.includes("/ui/pages/") && path.endsWith("Page.tsx"))
      .map((path) => basename(path))
      .sort();

    expect(actualPages).toEqual([...pageFiles].sort());
    expect(
      files
        .map((path) => relative(macroRoot, path))
        .filter((path) => /(registry|catalog|universal[-_]?renderer|module[-_]?view)/i.test(path)),
    ).toEqual([]);
  });

  it("wires the six stable routes and leaves retired routes unmatched", () => {
    const router = readSource("routes/router.tsx");

    for (const path of [
      'path: "macro"',
      'path: "macro/cross-asset"',
      'path: "macro/rates-inflation"',
      'path: "macro/growth-labor"',
      'path: "macro/liquidity-funding"',
      'path: "macro/credit"',
    ]) {
      expect(router).toContain(path);
    }
    expect(router).not.toContain('path: "macro/*"');
  });

  it("uses only the seven current Macro API paths", () => {
    const macroSource = macroText();
    const paths = [...macroSource.matchAll(/["`]\/api\/macro(?:\/[^"`]*)?["`]/g)].map((match) =>
      match[0].slice(1, -1),
    );

    expect(new Set(paths)).toEqual(
      new Set([
        "/api/macro/overview",
        "/api/macro/cross-asset",
        "/api/macro/rates-inflation",
        "/api/macro/growth-labor",
        "/api/macro/liquidity-funding",
        "/api/macro/credit",
        "/api/macro/series",
      ]),
    );
  });

  it("renders the strict v2 decision fields without frontend inference", () => {
    const overview = readFileSync(join(macroRoot, "ui/pages/MacroOverviewPage.tsx"), "utf8");

    for (const field of [
      "shock_summary",
      "risk_lanes",
      "key_changes",
      "nearest_catalyst",
      "core_invalidation",
    ]) {
      expect(overview).toContain(field);
    }
    expect(overview).toContain("data.risk_lanes.map");
    expect(overview).not.toMatch(/risk_lanes\.(?:sort|filter|reduce)/);
    expect(overview).not.toMatch(/\bdominant_shock\b|macro_evidence_v1/);
    expect(overview).not.toMatch(/buy|sell|holding|position.?size|allocation|target.?price|llm/i);
  });

  it("keeps normal audit metadata collapsed and local gaps adjacent", () => {
    const frame = readFileSync(join(macroRoot, "ui/MacroPageFrame.tsx"), "utf8");
    const overview = readFileSync(join(macroRoot, "ui/pages/MacroOverviewPage.tsx"), "utf8");

    expect(frame).toContain("<details");
    expect(frame).not.toMatch(/<details[^>]*\bopen\b/);
    for (const label of ["投影版本", "事实水位", "市场截止", "计算时间", "规则版本"]) {
      expect(frame).toContain(label);
    }
    expect(overview).toContain("lane.degradation_reason");
    expect(overview).toContain("macro-risk-lane-gap");
    expect(existsSync(join(macroRoot, "ui/MacroPageShell.tsx"))).toBe(false);
  });

  it("keeps unit-separated chart semantics and responsive feature CSS", () => {
    const chart = readFileSync(join(macroRoot, "ui/MacroSeriesPanel.tsx"), "utf8");
    const css = collectFiles(macroRoot)
      .filter((path) => path.endsWith(".css"))
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");

    for (const contract of [
      "20d",
      "60d",
      "series.sources",
      "macroUnitLabel(series.unit)",
      "latest?.observed_at",
      "<SeriesFigure",
    ]) {
      expect(chart).toContain(contract);
    }
    expect(css).toContain("@media (max-width: 1279px)");
    expect(css).toContain("@media (max-width: 767px)");
  });

  it("contains no v1 or prohibited output contract in supported Macro source", () => {
    const source = macroText();

    for (const retired of [
      "MacroWorkbench",
      "MacroModuleView",
      "MacroScenario",
      "MacroScorecard",
      "macro_regime_v4",
      "macro_evidence_v1",
      "trade_map",
      "scenario_cases",
    ]) {
      expect(source).not.toContain(retired);
    }
  });
});

function macroText(): string {
  return collectFiles(macroRoot)
    .filter((path) => path.endsWith(".ts") || path.endsWith(".tsx"))
    .map((path) => `${relative(macroRoot, path)}\n${readFileSync(path, "utf8")}`)
    .join("\n");
}

function readSource(path: string): string {
  return readFileSync(join(srcRoot, path), "utf8");
}

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
