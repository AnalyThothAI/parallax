import {
  buildMacroDataHealthBuckets,
  buildMacroEvidenceGroups,
  buildMacroMetrics,
  extraTables,
  macroReadSummary,
  primarySupportingTable,
} from "@features/macro/model/macroModulePresentation";
import { macroModuleFixture, macroOverviewModuleFixture } from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroModulePresentation", () => {
  it("normalizes metric labels without exposing raw keys", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        {
          concept_key: "asset:spx",
          label: "标普500",
          short_label: "SPX",
          display_value: "7473.47",
          unit_label: "点",
        },
        {
          concept_key: "vol:vix",
          label: "VIX",
          short_label: "VIX",
          display_value: "16.76",
        },
      ],
    });

    expect(metrics.map((metric) => metric.shortLabel)).toEqual(["SPX", "VIX"]);
    expect(metrics.map((metric) => metric.label)).toEqual(["标普500", "VIX"]);
    expect(metrics.map((metric) => metric.value)).toEqual(["7473.47", "16.76"]);
    expect(metrics[0]).toMatchObject({
      key: "asset:spx",
      unitLabel: "点",
    });
  });

  it("builds read, evidence, and health from v3 fields only", () => {
    const module = macroOverviewModuleFixture();

    expect(macroReadSummary(module)).toContain("总览");
    expect(buildMacroEvidenceGroups(module.module_evidence).map((group) => group.key)).toEqual([
      "confirmations",
      "contradictions",
      "watch_triggers",
      "invalidations",
    ]);
    expect(buildMacroDataHealthBuckets(module.data_health, "overview")).toHaveLength(4);
  });

  it("keeps supporting table helpers scoped to module tables", () => {
    const module = macroModuleFixture({
      tables: [
        { id: "primary", rows: [{ label: "Primary" }] },
        { id: "secondary", rows: [{ label: "Secondary" }] },
      ],
    });

    expect(primarySupportingTable(module).id).toBe("primary");
    expect(extraTables(module).map((table) => table.id)).toEqual(["secondary"]);
    expect(primarySupportingTable({ ...module, tables: [] }).id).toBe(
      "assets/equities_supporting_table",
    );
  });

  it("does not read retired top-level compatibility fields", () => {
    const module = macroOverviewModuleFixture({
      module_read: {
        headline: "总览：v3 字段",
      },
      module_evidence: {
        confirmations: [{ label: "v3 confirmation" }],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
      data_health: {
        summary_status: "ok",
        summary_label: "v3 health",
        module_gaps: [],
        chart_gaps: [],
        global_gaps: [{ label: "v3 gap" }],
        future_integration_gaps: [],
      },
      read: { headline: "legacy read" },
      evidence: { confirmations: [{ label: "legacy evidence" }] },
      data_gaps: [{ label: "legacy gap" }],
    });

    expect(macroReadSummary(module)).toBe("总览：v3 字段");
    expect(buildMacroEvidenceGroups(module.module_evidence)[0]?.items[0]?.label).toBe(
      "v3 confirmation",
    );
    expect(buildMacroDataHealthBuckets(module.data_health, "overview")[2]?.items).toEqual([
      "v3 gap",
    ]);
  });
});
