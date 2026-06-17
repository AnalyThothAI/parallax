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

  it("drops metric and evidence placeholders instead of formatting empty values", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        {
          concept_key: "asset:spx",
          label: "标普500",
          display_value: "7473.47",
        },
        {
          concept_key: "vol:vix",
          label: "VIX",
        },
      ],
    });

    expect(metrics).toHaveLength(1);
    expect(metrics[0]?.label).toBe("标普500");

    const groups = buildMacroEvidenceGroups({
      confirmations: [
        {
          code: "term_premium_up",
          label: "期限溢价上行",
          description: "10Y real yield pushes higher.",
        },
        { label: "缺少 identity", description: "no code" },
        { label: "空详情证据" },
        { description: "no label" },
      ],
      contradictions: [],
      watch_triggers: [],
      invalidations: [],
    });

    expect(groups[0]?.items).toEqual([
      {
        detail: "10Y real yield pushes higher.",
        key: "term_premium_up",
        label: "期限溢价上行",
      },
    ]);
    expect(JSON.stringify({ groups, metrics })).not.toContain("暂无");
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
    expect(
      buildMacroDataHealthBuckets(module.data_health, "overview").map((bucket) => bucket.key),
    ).toEqual(["module_gaps", "chart_gaps", "global_gaps"]);
  });

  it("does not infer module read summaries from snapshot status placeholders", () => {
    const module = macroOverviewModuleFixture({
      module_read: {},
      snapshot: {
        ...macroOverviewModuleFixture().snapshot,
        status: "partial",
        status_label: "部分可用",
      },
    });

    expect(macroReadSummary(module)).toBeNull();
  });

  it("preserves actionable data-health gap remediation instead of flattening gaps to strings", () => {
    const module = macroModuleFixture();

    expect(buildMacroDataHealthBuckets(module.data_health, "leaf")[0]?.items).toEqual([
      {
        detail: "回填 60 日宏观历史后重新投影。",
        key: "insufficient_history:60d",
        label: "历史样本不足：无法计算 60 日变化",
        severity: "warning",
        scope: null,
      },
    ]);
  });

  it("drops code-only data-health gaps instead of manufacturing labels", () => {
    const module = macroModuleFixture({
      data_health: {
        ...macroModuleFixture().data_health,
        module_gaps: [{ code: "basis_missing" }, {}],
      },
    });

    expect(buildMacroDataHealthBuckets(module.data_health, "leaf")[0]?.items).toEqual([]);
  });

  it("drops metrics and data-health gaps without backend identity instead of synthetic keys", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        {
          label: "标普500",
          display_value: "7473.47",
        },
      ],
    });
    const buckets = buildMacroDataHealthBuckets(
      macroModuleFixture({
        data_health: {
          ...macroModuleFixture().data_health,
          module_gaps: [{ label: "缺少宏观基差", remediation_hint: "补齐基差源。" }],
        },
      }).data_health,
      "leaf",
    );

    expect(metrics).toEqual([]);
    expect(buckets[0]?.items).toEqual([]);
    expect(JSON.stringify({ buckets, metrics })).not.toContain("metric:0");
    expect(JSON.stringify({ buckets, metrics })).not.toContain("module_gaps:0");
  });

  it("keeps supporting table helpers scoped to module tables without manufacturing empty shells", () => {
    const module = macroModuleFixture({
      tables: [
        { id: "primary", rows: [{ label: "Primary" }] },
        { id: "secondary", rows: [{ label: "Secondary" }] },
      ],
    });

    expect(primarySupportingTable(module)).toMatchObject({ id: "primary" });
    expect(extraTables(module).map((table) => table.id)).toEqual(["secondary"]);
    expect(primarySupportingTable({ ...module, tables: [] })).toBeNull();
  });

  it("does not read retired top-level compatibility fields", () => {
    const module = macroOverviewModuleFixture({
      module_read: {
        headline: "总览：v3 字段",
      },
      module_evidence: {
        confirmations: [
          { code: "v3_confirmation", label: "v3 confirmation", description: "v3 detail" },
        ],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
      data_health: {
        summary_status: "ok",
        summary_label: "v3 health",
        module_gaps: [],
        chart_gaps: [],
        global_gaps: [{ code: "v3_gap", label: "v3 gap" }],
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
      {
        detail: null,
        key: "v3_gap",
        label: "v3 gap",
        severity: null,
        scope: null,
      },
    ]);
  });
});
