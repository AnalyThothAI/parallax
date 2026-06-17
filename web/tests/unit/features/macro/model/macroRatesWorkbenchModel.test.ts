import {
  buildRatesWorkbenchView,
  humanizeRatesConceptKey,
  isRatesModuleId,
} from "@features/macro/model/macroRatesWorkbenchModel";
import {
  macroFedFundsModuleFixture,
  macroRealRatesModuleFixture,
  macroYieldCurveModuleFixture,
} from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroRatesWorkbenchModel", () => {
  it("identifies rates module ids", () => {
    expect(isRatesModuleId("rates/fed-funds")).toBe(true);
    expect(isRatesModuleId("assets/equities")).toBe(false);
    expect(isRatesModuleId("rates/expectations")).toBe(false);
  });

  it("does not manufacture rates market headlines from module titles and readiness", () => {
    const module = macroFedFundsModuleFixture();
    module.module_read = {
      ...module.module_read,
      headline: null,
    };

    const view = buildRatesWorkbenchView(module, "rates/fed-funds");

    expect(view.marketHeadline).toBeNull();
    expect(primaryWorkbenchText(view)).not.toContain("政策利率走廊：");
    expect(primaryWorkbenchText(view)).not.toContain("部分可用");
  });

  it("formats yield curve diagnostics from backend payload", () => {
    const view = buildRatesWorkbenchView(macroYieldCurveModuleFixture(), "rates/yield-curve");

    expect(view.curveDiagnostics?.headline).toBe("曲线诊断 · 熊陡");
    expect(view.curveDiagnostics?.summary).toBe(
      "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。",
    );
    expect(view.curveDiagnostics?.rows.map((row) => row.value)).toEqual([
      "40bp · 1w +10bp · 1m +10bp · 3m +10bp",
      "-10bp · 1w +25bp · 1m +40bp · 3m +60bp",
      "70bp · 1w +5bp · 1m 0bp · 3m 0bp",
    ]);
    expect(view.curveDiagnostics?.spreadHistories[0]).toMatchObject({
      label: "2s10s",
      latest: "40bp",
      range: "30bp 至 40bp",
      points: [
        { key: "2s10s:2026-02-19", label: "2026-02-19：30bp", value: 30 },
        { key: "2s10s:2026-04-20", label: "2026-04-20：30bp", value: 30 },
        { key: "2s10s:2026-05-13", label: "2026-05-13：30bp", value: 30 },
        { key: "2s10s:2026-05-20", label: "2026-05-20：40bp", value: 40 },
      ],
    });
    expect(view.curveDiagnostics?.tenorComparison).toEqual([
      {
        key: "5y",
        label: "5Y",
        value: "名义 4% · 实际 2.1% · 通胀补偿 1.9%",
        change: "1w：名义 +10bp · 实际 +15bp · 通胀补偿 -5bp",
        residual: "残差 0bp",
        driverLabel: "实际利率驱动",
      },
      {
        key: "10y",
        label: "10Y",
        value: "名义 4.2% · 实际 1.95% · 通胀补偿 2.15%",
        change: "1w：名义 +20bp · 实际 +15bp · 通胀补偿 -5bp",
        residual: "残差 10bp",
        driverLabel: "实际利率驱动",
      },
    ]);
    expect(primaryWorkbenchText(view)).toContain(
      "期限溢价压力：优先防守长久期成长、长债和高 beta。",
    );
    expect(primaryWorkbenchText(view)).not.toContain("rates:dgs");
  });

  it("formats fed funds policy diagnostics from backend payload", () => {
    const view = buildRatesWorkbenchView(macroFedFundsModuleFixture(), "rates/fed-funds");
    const policyDiagnostics = (
      view as typeof view & {
        policyDiagnostics?: {
          headline: string;
          implications: string[];
          invalidations: string[];
          rows: Array<{ label: string; statusLabel: string | null; value: string }>;
          summary: string;
        } | null;
      }
    ).policyDiagnostics;

    expect(policyDiagnostics?.headline).toBe("政策走廊诊断 · 走廊压力");
    expect(policyDiagnostics?.summary).toBe(
      "政策走廊承压：EFFR 高于目标上限且 SOFR 相对 EFFR 走阔，隔夜融资压力需要降杠杆。",
    );
    expect(policyDiagnostics?.rows.map((row) => row.value)).toEqual([
      "4.25%-4.5% · 宽度 25bp",
      "4.55% · 距上限 +5bp · 1w +20bp",
      "15bp · 1w +20bp",
      "7bp · 1w +6bp",
      "2bp · 1w +2bp",
      "-1bp · 1w 0bp",
      "8bp · 1w +6bp",
      "$102B · 1w -$43B",
      "$196B · 1w -$14B",
    ]);
    expect(primaryWorkbenchText(view)).toContain(
      "走廊压力：降低融资敏感资产和杠杆多头，等待 EFFR 回到目标区间内。",
    );
    expect(primaryWorkbenchText(view)).not.toMatch(/fed:|liquidity:/);
  });

  it("drops policy diagnostics rows without backend key or label", () => {
    const module = macroFedFundsModuleFixture();
    const diagnostics = module.module_read.policy_diagnostics as Record<string, unknown>;
    diagnostics.rows = [
      { label: "缺 key 的 EFFR", current_pct: 4.55 },
      { key: "iorb_without_label", current_pct: 4.4 },
      { key: "effr", label: "EFFR", current_pct: 4.55 },
    ];

    const view = buildRatesWorkbenchView(module, "rates/fed-funds");

    expect(view.policyDiagnostics?.rows.map((row) => row.label)).toEqual(["EFFR"]);
    expect(JSON.stringify(view.policyDiagnostics)).not.toContain("policy-row");
    expect(JSON.stringify(view.policyDiagnostics)).not.toContain("政策读数");
    expect(JSON.stringify(view.policyDiagnostics)).not.toContain("iorb_without_label");
  });

  it("drops policy diagnostics without backend label instead of using default copy", () => {
    const module = macroFedFundsModuleFixture();
    const diagnostics = { ...(module.module_read.policy_diagnostics as Record<string, unknown>) };
    delete diagnostics.label;
    module.module_read = {
      ...module.module_read,
      policy_diagnostics: diagnostics,
    };

    const view = buildRatesWorkbenchView(module, "rates/fed-funds");

    expect(view.policyDiagnostics).toBeNull();
    expect(primaryWorkbenchText(view)).not.toContain("政策走廊诊断");
  });

  it("formats real rate diagnostics from backend payload", () => {
    const view = buildRatesWorkbenchView(macroRealRatesModuleFixture(), "rates/real-rates");

    expect(view.realRateDiagnostics?.headline).toBe("实际利率诊断 · 实际利率压力");
    expect(view.realRateDiagnostics?.summary).toBe(
      "实际利率上行且通胀补偿未同步走阔：估值压力偏实际利率驱动，长久期与高 beta 需要降级。",
    );
    expect(view.realRateDiagnostics?.realYieldRows.map((row) => row.value)).toEqual([
      "2.05% · 1w +20bp · 1m +35bp · 3m +45bp",
      "2.1% · 1w +20bp · 1m +30bp · 3m +40bp",
    ]);
    expect(view.realRateDiagnostics?.inflationRows.map((row) => row.value)).toEqual([
      "2.15% · 1w -5bp · 1m -10bp · 3m -5bp",
      "2.25% · 1w -5bp · 1m -10bp · 3m -15bp",
    ]);
    expect(primaryWorkbenchText(view)).toContain(
      "实际利率压力：降低长久期成长、长债和高 beta 反弹置信度。",
    );
    expect(primaryWorkbenchText(view)).not.toMatch(/rates:|inflation:/);
  });

  it("drops curve diagnostics rows, histories, and tenors without backend identity or label", () => {
    const module = macroYieldCurveModuleFixture();
    const diagnostics = module.module_read.curve_diagnostics as Record<string, unknown>;
    diagnostics.rows = [
      { label: "缺 key 的 2s10s", current_bp: 40 },
      { key: "3m10y_without_label", current_bp: -10 },
      { key: "5s30s", label: "5s30s", current_bp: 70 },
    ];
    diagnostics.spread_history = [
      {
        label: "缺 key 的历史",
        points: [{ observed_at: "2026-05-20", value_bp: 40 }],
        latest_bp: 40,
      },
      {
        key: "history_without_label",
        points: [{ observed_at: "2026-05-20", value_bp: -10 }],
        latest_bp: -10,
      },
      {
        key: "point_without_date",
        label: "点缺日期",
        points: [{ value_bp: 20 }],
        latest_bp: 20,
      },
      {
        key: "5s30s",
        label: "5s30s",
        points: [{ observed_at: "2026-05-20", value_bp: 70 }],
        latest_bp: 70,
      },
    ];
    diagnostics.tenor_comparison = [
      {
        label: "缺 key 的 5Y",
        nominal_pct: 4,
        real_pct: 2.1,
        breakeven_pct: 1.9,
      },
      {
        key: "10y_without_label",
        nominal_pct: 4.2,
        real_pct: 1.95,
        breakeven_pct: 2.15,
      },
      {
        key: "30y",
        label: "30Y",
        nominal_pct: 4.5,
        real_pct: 2.2,
        breakeven_pct: 2.3,
      },
    ];

    const view = buildRatesWorkbenchView(module, "rates/yield-curve");

    expect(view.curveDiagnostics?.rows.map((row) => row.label)).toEqual(["5s30s"]);
    expect(view.curveDiagnostics?.spreadHistories.map((series) => series.label)).toEqual(["5s30s"]);
    expect(view.curveDiagnostics?.spreadHistories[0]?.points).toEqual([
      { key: "5s30s:2026-05-20", label: "2026-05-20：70bp", value: 70 },
    ]);
    expect(view.curveDiagnostics?.tenorComparison.map((row) => row.label)).toEqual(["30Y"]);
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("curve-row");
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("curve-history");
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("曲线 2");
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("利差历史");
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("期限 2");
    expect(JSON.stringify(view.curveDiagnostics)).not.toContain("点 1");
  });

  it("drops curve diagnostics without backend label instead of using default copy", () => {
    const module = macroYieldCurveModuleFixture();
    const diagnostics = { ...(module.module_read.curve_diagnostics as Record<string, unknown>) };
    delete diagnostics.label;
    module.module_read = {
      ...module.module_read,
      curve_diagnostics: diagnostics,
    };

    const view = buildRatesWorkbenchView(module, "rates/yield-curve");

    expect(view.curveDiagnostics).toBeNull();
    expect(primaryWorkbenchText(view)).not.toContain("曲线诊断");
  });

  it("drops real-rate diagnostics rows without backend key or label", () => {
    const module = macroRealRatesModuleFixture();
    const diagnostics = module.module_read.real_rate_diagnostics as Record<string, unknown>;
    diagnostics.real_yield_rows = [
      { label: "缺 key 的 5Y Real", current_pct: 2.05 },
      { key: "10y_real_without_label", current_pct: 2.1 },
      { key: "30y_real", label: "30Y Real", current_pct: 2.2 },
    ];
    diagnostics.inflation_rows = [
      { label: "缺 key 的 5Y Breakeven", current_pct: 2.15 },
      { key: "10y_breakeven_without_label", current_pct: 2.25 },
      { key: "30y_breakeven", label: "30Y Breakeven", current_pct: 2.3 },
    ];

    const view = buildRatesWorkbenchView(module, "rates/real-rates");

    expect(view.realRateDiagnostics?.realYieldRows.map((row) => row.label)).toEqual(["30Y Real"]);
    expect(view.realRateDiagnostics?.inflationRows.map((row) => row.label)).toEqual([
      "30Y Breakeven",
    ]);
    expect(JSON.stringify(view.realRateDiagnostics)).not.toContain("实际利率读数");
    expect(JSON.stringify(view.realRateDiagnostics)).not.toContain("10y_real_without_label");
    expect(JSON.stringify(view.realRateDiagnostics)).not.toContain("10y_breakeven_without_label");
  });

  it("drops real-rate diagnostics without backend label instead of using default copy", () => {
    const module = macroRealRatesModuleFixture();
    const diagnostics = {
      ...(module.module_read.real_rate_diagnostics as Record<string, unknown>),
    };
    delete diagnostics.label;
    module.module_read = {
      ...module.module_read,
      real_rate_diagnostics: diagnostics,
    };

    const view = buildRatesWorkbenchView(module, "rates/real-rates");

    expect(view.realRateDiagnostics).toBeNull();
    expect(primaryWorkbenchText(view)).not.toContain("实际利率诊断");
  });

  it("humanizes rates keys and builds neutral ready module facts", () => {
    const fedFunds = buildRatesWorkbenchView(macroFedFundsModuleFixture(), "rates/fed-funds");
    const realRates = buildRatesWorkbenchView(macroRealRatesModuleFixture(), "rates/real-rates");

    expect(humanizeRatesConceptKey("rates:dgs10")).toBe("10年期美债收益率");
    expect(humanizeRatesConceptKey("rates:not_mapped")).toBeNull();
    expect(fedFunds.facts.map((fact) => fact.label)).toContain("EFFR");
    expect(realRates.marketHeadline).toContain("实际利率");
    expect(primaryWorkbenchText(fedFunds)).not.toContain("fed:effr");
  });

  it("drops rates facts without backend concept key or label instead of manufacturing facts", () => {
    const view = buildRatesWorkbenchView(
      {
        ...macroFedFundsModuleFixture(),
        tiles: [
          {
            label: "缺 concept key 的事实",
            display_value: "4.55%",
          },
          {
            concept_key: "fed:effr",
            display_value: "4.55%",
          },
          {
            concept_key: "fed:iorb",
            label: "IORB",
            display_value: "4.40%",
          },
        ],
      },
      "rates/fed-funds",
    );

    expect(view.facts.map((fact) => fact.label)).toEqual(["IORB"]);
    expect(JSON.stringify(view.facts)).not.toContain("fact:");
    expect(JSON.stringify(view.facts)).not.toContain("缺 concept key 的事实");
  });

  it("drops unknown missing concept ids instead of humanizing raw concept fragments", () => {
    const module = macroYieldCurveModuleFixture();
    module.primary_chart = {
      ...module.primary_chart,
      missing_concept_keys: ["rates:dgs10", "rates:not_mapped"],
    };

    const view = buildRatesWorkbenchView(module, "rates/yield-curve");

    expect(view.missingPrimaryItems).toContain("10年期美债收益率");
    expect(view.missingPrimaryItems.join("\n")).not.toContain("NOT MAPPED");
    expect(view.missingPrimaryItems.join("\n")).not.toContain("rates:not_mapped");
  });

  it("drops rates facts whose value formats to empty", () => {
    const view = buildRatesWorkbenchView(
      {
        ...macroFedFundsModuleFixture(),
        tiles: [
          {
            concept_key: "fed:effr",
            label: "EFFR",
            display_value: "4.55%",
          },
          {
            concept_key: "rates:empty",
            label: "空利率事实",
            display_value: "暂无",
          },
        ],
      },
      "rates/fed-funds",
    );

    expect(view.facts.map((fact) => fact.label)).toEqual(["EFFR"]);
    expect(primaryWorkbenchText(view)).not.toContain("空利率事实");
    expect(primaryWorkbenchText(view)).not.toContain("暂无");
  });

  it("drops rates gap summaries without backend code or label instead of humanizing codes", () => {
    const module = macroFedFundsModuleFixture();
    module.data_health = {
      ...module.data_health,
      module_gaps: [
        { label: "缺 code 的缺口", severity: "warning" },
        { code: "rates:not_mapped_gap", severity: "warning" },
        { code: "sofr_30d_missing", label: "SOFR 30D 尚未入库", severity: "info" },
      ],
      chart_gaps: [{ code: "chart_gap_without_label", severity: "warning" }],
    };

    const view = buildRatesWorkbenchView(module, "rates/fed-funds");

    expect(view.diagnostics.coverage).toEqual([
      {
        key: "sofr_30d_missing",
        label: "SOFR 30D 尚未入库",
        severity: "info",
      },
    ]);
    expect(view.missingPrimaryItems).toContain("SOFR 30D 尚未入库");
    expect(view.missingPrimaryItems.join("\n")).not.toContain("NOT MAPPED GAP");
    expect(JSON.stringify(view.diagnostics.coverage)).not.toContain("gap:");
    expect(JSON.stringify(view.diagnostics.coverage)).not.toContain("not_mapped_gap");
    expect(JSON.stringify(view.diagnostics.coverage)).not.toContain("chart_gap_without_label");
  });
});

function primaryWorkbenchText(view: {
  title: string;
  question: string;
  marketHeadline: string | null;
  facts: Array<{
    interpretation: string | null;
    label: string;
    observedAtLabel: string | null;
    sourceLabel: string | null;
    statusLabel: string | null;
    value: string;
  }>;
  missingPrimaryItems: string[];
  proxyNote: string | null;
  chartTitle: string | null;
  chartNote: string | null;
  decisionGroups: Array<{ items: Array<{ detail: string | null; label: string }>; label: string }>;
  curveDiagnostics?: {
    headline: string;
    implications: string[];
    invalidations: string[];
    rows: Array<{ value: string; label: string; statusLabel: string | null }>;
    summary: string;
  } | null;
  policyDiagnostics?: {
    headline: string;
    implications: string[];
    invalidations: string[];
    rows: Array<{ value: string; label: string; statusLabel: string | null }>;
    summary: string;
  } | null;
  realRateDiagnostics?: {
    headline: string;
    implications: string[];
    inflationRows: Array<{ value: string; label: string; statusLabel: string | null }>;
    invalidations: string[];
    realYieldRows: Array<{ value: string; label: string; statusLabel: string | null }>;
    summary: string;
  } | null;
}): string {
  return [
    view.title,
    view.question,
    view.marketHeadline,
    view.proxyNote,
    view.chartTitle,
    view.chartNote,
    view.curveDiagnostics?.headline,
    view.curveDiagnostics?.summary,
    view.policyDiagnostics?.headline,
    view.policyDiagnostics?.summary,
    view.realRateDiagnostics?.headline,
    view.realRateDiagnostics?.summary,
    ...(view.curveDiagnostics?.rows.flatMap((row) => [row.label, row.value, row.statusLabel]) ??
      []),
    ...(view.policyDiagnostics?.rows.flatMap((row) => [row.label, row.value, row.statusLabel]) ??
      []),
    ...(view.realRateDiagnostics?.realYieldRows.flatMap((row) => [
      row.label,
      row.value,
      row.statusLabel,
    ]) ?? []),
    ...(view.realRateDiagnostics?.inflationRows.flatMap((row) => [
      row.label,
      row.value,
      row.statusLabel,
    ]) ?? []),
    ...(view.curveDiagnostics?.implications ?? []),
    ...(view.curveDiagnostics?.invalidations ?? []),
    ...(view.policyDiagnostics?.implications ?? []),
    ...(view.policyDiagnostics?.invalidations ?? []),
    ...(view.realRateDiagnostics?.implications ?? []),
    ...(view.realRateDiagnostics?.invalidations ?? []),
    ...view.missingPrimaryItems,
    ...view.facts.flatMap((fact) => [
      fact.label,
      fact.value,
      fact.observedAtLabel,
      fact.sourceLabel,
      fact.statusLabel,
      fact.interpretation,
    ]),
    ...view.decisionGroups.flatMap((group) => [
      group.label,
      ...group.items.flatMap((item) => [item.label, item.detail]),
    ]),
  ]
    .filter(Boolean)
    .join("\n");
}
