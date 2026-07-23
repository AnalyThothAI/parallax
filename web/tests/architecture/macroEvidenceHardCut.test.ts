import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
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

describe("macro evidence frontend hard cut", () => {
  it("owns exactly six explicit pages without a registry or universal renderer", () => {
    const files = collectFiles(macroRoot);
    const actualPages = files
      .filter((path) => path.includes("/ui/pages/") && path.endsWith("Page.tsx"))
      .map((path) => path.split("/").at(-1))
      .sort();

    expect(actualPages).toEqual([...pageFiles].sort());
    expect(
      files.filter((path) => /(registry|catalog|renderer|workbench|module)/i.test(path)),
    ).toEqual([]);
  });

  it("wires six flat routes and leaves retired routes unmatched", () => {
    const router = readFileSync(join(srcRoot, "routes/router.tsx"), "utf8");

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
    expect(router).not.toContain("macro.route");
    expect(existsSync(join(srcRoot, "routes/macro.route.tsx"))).toBe(false);
  });

  it("uses only the seven current macro API paths", () => {
    const macroSource = collectFiles(macroRoot)
      .filter((path) => path.endsWith(".ts") || path.endsWith(".tsx"))
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");
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
    expect(macroSource).not.toMatch(/\/api\/macro\/modules|asset-correlation/);
  });

  it("contains no legacy macro product contract in supported frontend source", () => {
    const source = collectFiles(srcRoot)
      .filter((path) => path.endsWith(".ts") || path.endsWith(".tsx"))
      .filter((path) => !path.endsWith("/lib/types/openapi.ts"))
      .map((path) => `${relative(webRoot, path)}\n${readFileSync(path, "utf8")}`)
      .join("\n");

    for (const retired of [
      "MacroWorkbench",
      "MacroModuleView",
      "MacroScenario",
      "MacroScorecard",
      "MacroAssetCorrelation",
      "macro_regime_v4",
      "trade_map",
      "scenario_cases",
    ]) {
      expect(source).not.toContain(retired);
    }
  });

  it("keeps complete metadata and responsive breakpoints in feature-owned CSS", () => {
    const shell = readFileSync(join(macroRoot, "ui/MacroPageShell.tsx"), "utf8");
    const evidence = readFileSync(join(macroRoot, "ui/MacroEvidenceBlocks.tsx"), "utf8");
    const renderedContract = `${shell}\n${evidence}`;
    const css = collectFiles(macroRoot)
      .filter((path) => path.endsWith(".css"))
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");

    for (const label of [
      "投影版本",
      "事实水位",
      "市场截止",
      "计算时间",
      "判断期限",
      "规则版本",
      "驱动",
      "确认",
      "反证",
      "升级 / 失效",
      "实际规则命中",
      "未评估能力",
    ]) {
      expect(renderedContract).toContain(label);
    }
    for (const label of [
      "变化窗口",
      "观测日",
      "频率",
      "来源",
      "序列",
      "新鲜度",
      "样本",
      "质量",
      "关键性",
      "主张作用",
      "推导",
    ]) {
      expect(evidence).toContain(label);
    }
    expect(css).toContain("@media (max-width: 1279px)");
    expect(css).toContain("@media (max-width: 767px)");
    expect(css).not.toContain("overflow-x:");
  });
});

function collectFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const path = join(root, entry);
    return statSync(path).isDirectory() ? collectFiles(path) : [path];
  });
}
