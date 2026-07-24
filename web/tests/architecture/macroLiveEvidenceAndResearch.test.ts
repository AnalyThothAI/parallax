import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "../..");
const macroRoot = join(webRoot, "src/features/macro");
const srcRoot = join(webRoot, "src");

describe("macro live evidence and research hard cut", () => {
  it("owns one live evidence page, one research page, and no page hierarchy", () => {
    const files = collectFiles(macroRoot).map((path) => relative(macroRoot, path));

    expect(files.filter((path) => path.endsWith(".tsx"))).toEqual([
      "ui/MacroLiveEvidencePage.tsx",
      "ui/MacroResearchPage.tsx",
    ]);
    expect(files).not.toContain("shell.ts");
    expect(files.some((path) => path.includes("/pages/"))).toBe(false);
    expect(files.some((path) => /(registry|catalog|universal[-_]?renderer)/i.test(path))).toBe(
      false,
    );
  });

  it("wires the dashboard, research document, and all six data detail routes", () => {
    const router = readSource("routes/router.tsx");

    expect(router.match(/path: "macro"/g)).toHaveLength(1);
    expect(router).toContain('path: "macro/research"');
    for (const viewId of [
      "overview",
      "rates-inflation",
      "growth-labor",
      "liquidity-funding",
      "credit",
      "cross-asset",
    ]) {
      expect(router).toContain(`["${viewId}", "${viewId}"]`);
    }
    expect(router).toContain("path: `macro/${path}`");
  });

  it("uses one persisted-only live API family and one completed-session research API", () => {
    const source = macroText();
    const paths = [...source.matchAll(/["`]\/api\/macro(?:\/[^"`]*)?["`]/g)].map((match) =>
      match[0].slice(1, -1),
    );

    expect(new Set(paths)).toEqual(
      new Set(["/api/macro/evidence/${viewId}", "/api/macro/research"]),
    );
    expect(source).not.toMatch(
      /macro_decision_v2|risk_lanes|daily.?judgment|useMacroSeries|useMacroOverview/i,
    );
    expect(source).not.toMatch(/\bpostApi\b|dangerouslySetInnerHTML|direction|confidence|gate/i);
  });

  it("renders dynamic sections, gaps, citations, and audit without frontend judgment", () => {
    const page = readFileSync(join(macroRoot, "ui/MacroResearchPage.tsx"), "utf8");

    for (const field of [
      "publication.sections.map",
      "publication.evidence_gaps.map",
      "publication.citations.map",
      "publication.reviewer_notes.map",
      "publication.audit",
    ]) {
      expect(page).toContain(field);
    }
    expect(page).not.toMatch(/score|direction|confidence|readiness|no_call|buy|sell|position/i);
  });

  it("keeps both feature surfaces namespaced, responsive, and bounded", () => {
    const researchCss = readFileSync(join(macroRoot, "ui/MacroResearchPage.css"), "utf8");
    const liveCss = [
      readFileSync(join(macroRoot, "ui/MacroLiveEvidencePage.css"), "utf8"),
      readFileSync(join(macroRoot, "ui/MacroLiveEvidenceResponsive.css"), "utf8"),
    ].join("\n");
    const researchSelectors = [...researchCss.matchAll(/(?<![\w-])\.([a-z][\w-]*)/g)].map(
      (match) => match[1],
    );
    const liveSelectors = [...liveCss.matchAll(/(?<![\w-])\.([a-z][\w-]*)/g)].map(
      (match) => match[1],
    );

    for (const file of [
      "MacroLiveEvidencePage.css",
      "MacroLiveEvidenceResponsive.css",
      "MacroResearchPage.css",
    ]) {
      expect(
        readFileSync(join(macroRoot, "ui", file), "utf8").split("\n").length,
      ).toBeLessThanOrEqual(500);
    }
    expect(researchCss).toContain("@layer app.features");
    expect(researchCss).toContain("@media (max-width: 767px)");
    expect(researchCss).toContain("overflow-wrap: anywhere");
    expect(liveCss).toContain("@layer app.features");
    expect(liveCss).toContain("@media (max-width: 767px)");
    expect(liveCss).toContain("overflow-wrap: anywhere");
    expect(researchSelectors.every((selector) => selector.startsWith("macro-research-"))).toBe(
      true,
    );
    expect(liveSelectors.every((selector) => selector.startsWith("macro-live-"))).toBe(true);
  });
});

function readSource(path: string): string {
  return readFileSync(join(srcRoot, path), "utf8");
}

function macroText(): string {
  return collectFiles(macroRoot)
    .filter((path) => /\.(?:ts|tsx)$/.test(path))
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");
}

function collectFiles(root: string): string[] {
  return readdirSync(root)
    .flatMap((entry) => {
      const path = join(root, entry);
      return statSync(path).isDirectory() ? collectFiles(path) : [path];
    })
    .sort();
}
