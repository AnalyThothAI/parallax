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
          evidence_label: "10Y real yield pushes higher.",
        },
        {
          key: "legacy_key_confirmation",
          label: "旧证据",
          evidence_label: "Legacy key-only evidence must stay internal.",
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
    expect(JSON.stringify(groups)).not.toContain("legacy_key_confirmation");
    expect(JSON.stringify(groups)).not.toContain("旧证据");
  });

  it("does not expose module evidence descriptions without evidence labels", () => {
    const groups = buildMacroEvidenceGroups({
      confirmations: [
        {
          code: "description_only_confirmation",
          label: "描述型确认",
          description: "raw module evidence description",
        },
        {
          code: "labeled_confirmation",
          label: "显式确认",
          description: "description remains structured",
          evidence_label: "backend display evidence",
        },
      ],
      contradictions: [],
      watch_triggers: [],
      invalidations: [],
    });

    expect(groups[0]?.items).toEqual([
      {
        detail: "backend display evidence",
        key: "labeled_confirmation",
        label: "显式确认",
      },
    ]);
    expect(JSON.stringify(groups)).not.toContain("raw module evidence description");
  });

  it("does not expose raw metric tile values without backend display values", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        {
          concept_key: "asset:spx",
          label: "标普500",
          value: 6500,
        },
        {
          concept_key: "rates:us10y",
          label: "10Y",
          display_value: "4.25%",
          value: 4.25,
        },
      ],
    });

    expect(metrics).toEqual([
      {
        key: "rates:us10y",
        label: "10Y",
        observedAtLabel: null,
        quality: null,
        qualityLabel: null,
        shortLabel: null,
        unitLabel: null,
        value: "4.25%",
      },
    ]);
    expect(JSON.stringify(metrics)).not.toContain("6500");
  });

  it("does not expose metric quality or delta labels as observed-at labels", () => {
    const metrics = buildMacroMetrics({
      tiles: [
        {
          concept_key: "asset:spx",
          label: "标普500",
          display_value: "7473.47",
          quality_label: "可用",
          delta_label: "1w +2%",
        },
        {
          concept_key: "rates:us10y",
          label: "10Y",
          display_value: "4.25%",
          observed_at_label: "观测于 2026-06-21",
          quality_label: "可用",
        },
      ],
    });

    expect(metrics.map((metric) => metric.observedAtLabel)).toEqual([null, "观测于 2026-06-21"]);
    expect(JSON.stringify(metrics)).not.toContain("1w +2%");
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

  it("does not use module regime labels as read summaries", () => {
    const module = macroOverviewModuleFixture({
      module_read: {
        regime_label: "状态标签不能替代摘要",
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

  it("does not expose generic data-health detail fields as actionable remediation", () => {
    const buckets = buildMacroDataHealthBuckets(
      {
        summary_status: "partial",
        summary_label: "部分可用",
        module_gaps: [
          {
            code: "description_only_gap",
            label: "描述型缺口",
            description: "raw descriptive gap copy",
          },
          {
            code: "explicit_detail_gap",
            label: "显式缺口",
            detail: "同步缺失序列后重新投影。",
          },
          {
            code: "explicit_remediation_gap",
            label: "可操作缺口",
            detail: "generic detail stays internal",
            remediation_hint: "补齐缺失序列后重新投影。",
          },
        ],
        chart_gaps: [],
        global_gaps: [],
      },
      "leaf",
    );

    expect(buckets[0]?.items).toEqual([
      {
        detail: null,
        key: "description_only_gap",
        label: "描述型缺口",
        scope: null,
        severity: null,
      },
      {
        detail: null,
        key: "explicit_detail_gap",
        label: "显式缺口",
        scope: null,
        severity: null,
      },
      {
        detail: "补齐缺失序列后重新投影。",
        key: "explicit_remediation_gap",
        label: "可操作缺口",
        scope: null,
        severity: null,
      },
    ]);
    expect(JSON.stringify(buckets)).not.toContain("raw descriptive gap copy");
    expect(JSON.stringify(buckets)).not.toContain("同步缺失序列后重新投影。");
    expect(JSON.stringify(buckets)).not.toContain("generic detail stays internal");
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
          {
            code: "v3_confirmation",
            label: "v3 confirmation",
            description: "legacy detail",
            evidence_label: "v3 detail",
          },
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
