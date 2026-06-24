import {
  buildMacroAssetClassDiagnostics,
  buildMacroCreditDiagnostics,
  buildMacroDecisionConsole,
  buildMacroEmploymentDiagnostics,
  buildMacroGrowthDiagnostics,
  buildMacroInflationDiagnostics,
  buildMacroLiquidityDiagnostics,
  buildMacroMarketEventFlow,
  buildMacroStructuredAnalysis,
  buildMacroWorkbenchBrief,
  buildMacroWorkbenchDrivers,
  hasMacroWorkbenchBrief,
  hasMacroWorkbenchDrivers,
  buildMacroVolatilityDiagnostics,
  buildMacroWorkbenchDiagnostics,
} from "@features/macro/model/macroWorkbenchModel";
import {
  macroCreditStressModuleFixture,
  macroEmploymentModuleFixture,
  macroGdpModuleFixture,
  macroInflationModuleFixture,
  macroLiquidityRrpTgaModuleFixture,
  macroModuleFixture,
  macroOverviewModuleFixture,
  macroVolatilityVixModuleFixture,
} from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroWorkbenchModel", () => {
  it("keeps missing module-read summaries empty instead of using snapshot status as copy", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {},
        snapshot: {
          ...macroOverviewModuleFixture().snapshot,
          status: "partial",
          status_label: "部分可用",
        },
      }),
    );

    expect(brief.summary).toBeNull();
    expect(brief.statusLabel).toBe("部分可用");
    expect(hasMacroWorkbenchBrief(brief)).toBe(false);
  });

  it("does not expose raw snapshot status codes as workbench brief labels", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {},
        snapshot: {
          ...macroOverviewModuleFixture().snapshot,
          status: "provider_not_configured",
          status_label: null,
        },
      }),
    );

    expect(brief.statusLabel).toBeNull();
    expect(JSON.stringify(brief)).not.toContain("provider_not_configured");
  });

  it("does not expose raw snapshot as-of dates as workbench brief labels", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {},
        snapshot: {
          ...macroOverviewModuleFixture().snapshot,
          asof_date: "2026-06-10",
          asof_label: null,
        },
      }),
    );

    expect(brief.asOfLabel).toBeNull();
    expect(JSON.stringify(brief)).not.toContain("2026-06-10");
  });

  it("does not expose raw module-read regimes as workbench brief labels", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {
          confidence_label: "真实覆盖说明",
          regime: "raw_regime_code",
        },
      }),
    );

    expect(brief.rows).toEqual([
      { key: "confidence_label", label: "规则覆盖", value: "真实覆盖说明" },
    ]);
    expect(JSON.stringify(brief)).not.toContain("raw_regime_code");
  });

  it("drops module-read rows whose formatted scalar value is empty", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {
          regime_label: { raw: true },
          confidence_label: "",
        },
      }),
    );

    expect(brief.rows).toEqual([]);
    expect(JSON.stringify(brief)).not.toContain("暂无");
    expect(hasMacroWorkbenchBrief(brief)).toBe(false);
  });

  it("does not expose boolean module-read fields as workbench brief labels", () => {
    const brief = buildMacroWorkbenchBrief(
      macroOverviewModuleFixture({
        module_read: {
          confidence_label: false,
          regime_label: true,
        },
      }),
    );

    expect(brief.rows).toEqual([]);
    expect(JSON.stringify(brief)).not.toContain("是");
    expect(JSON.stringify(brief)).not.toContain("否");
    expect(hasMacroWorkbenchBrief(brief)).toBe(false);
  });

  it("labels missing provenance as a zero source count instead of placeholder copy", () => {
    const diagnostics = buildMacroWorkbenchDiagnostics(
      macroOverviewModuleFixture({ provenance: { rows: [] } }),
      "overview",
    );

    expect(diagnostics.sourceMeta).toBe("0 个来源");
    expect(diagnostics.sourceCount).toBe(0);
  });

  it("does not expose raw diagnostics summary status codes as labels", () => {
    const diagnostics = buildMacroWorkbenchDiagnostics(
      macroOverviewModuleFixture({
        data_health: {
          ...macroOverviewModuleFixture().data_health,
          summary_label: null,
          summary_status: "ok",
          module_gaps: [],
          chart_gaps: [],
          global_gaps: [],
        },
      }),
      "overview",
    );

    expect(diagnostics.statusLabel).toBeNull();
    expect(JSON.stringify(diagnostics)).not.toContain('"ok"');
  });

  it("treats empty driver evidence and transmission as no panel content", () => {
    const drivers = buildMacroWorkbenchDrivers(
      macroModuleFixture({
        module_evidence: {
          confirmations: [],
          contradictions: [],
          watch_triggers: [],
          invalidations: [],
        },
        transmission: [],
      }),
    );

    expect(drivers.evidenceCount).toBe(0);
    expect(drivers.transmissionCount).toBe(0);
    expect(hasMacroWorkbenchDrivers(drivers)).toBe(false);
  });

  it("formats growth diagnostics as growth-cycle decision labels", () => {
    const diagnostics = buildMacroGrowthDiagnostics(macroGdpModuleFixture());

    expect(diagnostics?.headline).toBe("增长诊断 · 增长降温");
    expect(diagnostics?.summary).toBe(
      "增长降温：实际 GDP、工业生产和消费动能同步放缓，风险资产盈利预期需要降级。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "1.9% y/y · 1q -0.8pp",
      "1.5% SAAR · 1m -1.7pp",
      "-1.5% y/y · 1m -2pp",
      "1.3M · 1m -150k",
      "1.5% y/y · 1m -1pp",
      "1% y/y · 1m -2pp",
    ]);
    expect(diagnostics?.implications).toContain(
      "增长降温：降低盈利周期和高 beta 暴露，等待就业或消费重新确认。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("economy:gdp_real");
  });

  it("formats employment diagnostics as labor-market decision labels", () => {
    const diagnostics = buildMacroEmploymentDiagnostics(macroEmploymentModuleFixture());

    expect(diagnostics?.headline).toBe("就业诊断 · 就业降温");
    expect(diagnostics?.summary).toBe(
      "就业降温：失业率与初请上行、非农动能放缓，增长风险开始压过软着陆叙事。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "4.3% · 1m +0.3pp",
      "80k · 1m -140k",
      "260k · 1w +4k · 1m +30k",
      "7.4M · 1m -0.6M",
      "3.7% y/y · 1m -0.9pp",
    ]);
    expect(diagnostics?.implications).toContain(
      "就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀同步配合。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("labor:payrolls");
  });

  it("formats inflation diagnostics as y/y and breakeven labels", () => {
    const diagnostics = buildMacroInflationDiagnostics(macroInflationModuleFixture());

    expect(diagnostics?.headline).toBe("通胀诊断 · 通胀再加速");
    expect(diagnostics?.summary).toBe(
      "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "5.3% y/y · 1m +1.3pp",
      "5.7% y/y · 1m +1.3pp",
      "6.9% y/y · 1m +0.9pp",
      "2.6% · 1w +10bp · 1m +25bp",
    ]);
    expect(diagnostics?.implications).toContain(
      "通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("inflation:cpi");
  });

  it("formats liquidity diagnostics as corridor and balance-sheet labels", () => {
    const diagnostics = buildMacroLiquidityDiagnostics(macroLiquidityRrpTgaModuleFixture());

    expect(diagnostics?.headline).toBe("流动性诊断 · 走廊抽水");
    expect(diagnostics?.summary).toBe(
      "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "7bp · 1w +6bp · 1m +11bp",
      "9bp · 1w +5bp · 1m +8bp",
      "$3023B · 1w +$173B · 1m +$323B",
      "$760B · 1w -$60B · 1m -$140B",
      "$760B · 1w +$70B · 1m +$160B",
      "$5.78T · 1w -$60B · 1m -$120B",
    ]);
    expect(diagnostics?.implications).toContain(
      "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("liquidity:on_rrp");
  });

  it("formats overview liquidity pressure as a decision-console block", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.liquidityPressure).toEqual({
      detail: "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
      drivers: [
        "SOFR-IORB 走廊压力 · 7bp · 1w +6bp · 1m +11bp · 走廊压力",
        "净流动性 · $5.78T · 1w -$60B · 1m -$120B · 净抽水",
        "TGA 财政现金 · $760B · 1w +$70B · 1m +$160B · 财政抽水",
      ],
      implication: "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
      invalidation: "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
      key: "liquidity_pressure",
      label: "流动性压力",
      meta: "7.0/10 · 走廊抽水",
    });
    expect(JSON.stringify(consoleModel.liquidityPressure)).not.toContain("liquidity/rrp-tga");
  });

  it("drops liquidity pressure blocks without backend key or label", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const pressure = {
      key: "liquidity_pressure",
      label: "流动性压力",
      summary: "真实流动性压力描述。",
    };
    const withoutKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          liquidity_pressure: {
            label: "流动性压力",
            summary: "真实流动性压力描述。",
          },
        },
      },
    });
    const withoutLabel = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          liquidity_pressure: {
            ...pressure,
            label: undefined,
          },
        },
      },
    });

    expect(buildMacroDecisionConsole(withoutKey).liquidityPressure).toBeNull();
    expect(buildMacroDecisionConsole(withoutLabel).liquidityPressure).toBeNull();
  });

  it("formats overview top changes with backend source evidence", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.topChanges[0]).toEqual({
      detail: "SOFR-IORB +7bp · 最新 7bp · source=NY Fed / Federal Reserve · as-of=2026-05-20",
      key: "sofr_above_iorb",
      label: "SOFR 高于 IORB",
      meta: "SOFR-IORB +7bp · 最新 7bp · NY Fed / Federal Reserve · 2026-05-20 · 高",
    });
    expect(JSON.stringify(consoleModel.topChanges[0])).not.toContain("资金面");
  });

  it("formats overview future 24/72h catalysts from backend payload", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.futureCatalysts).toEqual([
      {
        detail: "10Y real yield keeps rising.",
        key: "watch:real_yield_breakout",
        label: "实际利率突破",
        meta: "24h · 高 · 情景触发",
        sourceUrl: null,
      },
      {
        detail: "2026-06-17 · 还有 1 天 · 14:00 ET",
        key: "event:official_calendar:fomc_decision_next",
        label: "FOMC 决议",
        meta: "24h · 高 · 官方日历",
        sourceUrl: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
      },
      {
        detail: "HY OAS crosses distress thresholds.",
        key: "watch:hy_oas_distress",
        label: "高收益债利差进入困境区",
        meta: "72h · 中 · 情景触发",
        sourceUrl: null,
      },
    ]);
  });

  it("drops future catalysts without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          future_catalysts: {
            label: "未来 24/72h 催化剂",
            rows: [
              { label: "无身份催化剂", description: "Should not keep a synthetic key." },
              {
                key: "legacy_description_catalyst",
                label: "旧正文催化剂",
                description: "Legacy future catalyst description must stay internal.",
              },
              {
                code: "legacy_code_catalyst",
                label: "旧催化剂",
                description: "Legacy code-only identity must stay internal.",
              },
              { key: "real_catalyst", label: "真实催化剂", detail: "Uses backend detail." },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.futureCatalysts.map((item) => item.key)).toEqual(["real_catalyst"]);
    expect(JSON.stringify(consoleModel)).not.toContain("future-catalyst:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无身份催化剂");
    expect(JSON.stringify(consoleModel)).not.toContain("legacy_description_catalyst");
    expect(JSON.stringify(consoleModel)).not.toContain(
      "Legacy future catalyst description must stay internal",
    );
    expect(JSON.stringify(consoleModel)).not.toContain("legacy_code_catalyst");
    expect(JSON.stringify(consoleModel)).not.toContain("旧催化剂");
  });

  it("does not expose raw future catalyst windows without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          future_catalysts: {
            key: "future_catalysts",
            label: "未来 24/72h 催化剂",
            rows: [
              {
                key: "watch:raw_window",
                label: "裸窗口催化剂",
                detail: "Raw window must stay internal.",
                window: "raw-window-24h",
                severity_label: "高",
                source: "情景触发",
              },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.futureCatalysts).toEqual([
      {
        detail: "Raw window must stay internal.",
        key: "watch:raw_window",
        label: "裸窗口催化剂",
        meta: "高 · 情景触发",
        sourceUrl: null,
      },
    ]);
    expect(JSON.stringify(consoleModel.futureCatalysts)).not.toContain("raw-window-24h");
  });

  it("formats overview judgement review from backend holding-period evidence", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.judgementReview).toEqual({
      itemCountLabel: "1 条",
      key: "judgement_review",
      label: "昨日判断复盘",
      rows: [
        {
          detail:
            "1D 已完成 · 5/5 · P&L +$100 · 均值 +1.00% / 5D 已完成 · 4/5 · P&L +$220 · 均值 +2.20% / 20D 观察中 · 2/5 · P&L -$80 · 均值 -0.80%",
          key: "risk_down_credit_sensitive:holding_periods",
          label: "风险降档 / 信用敏感",
          meta: "历史可信度 73.3% · 中 · 15 个样本",
        },
      ],
    });
  });

  it("drops judgement review sections and rows without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const holdingPeriodRow = {
      label: "真实复盘",
      windows: [
        {
          label: "1D",
          status_label: "已完成",
          win_rate_label: "1/1",
          pnl_usd: 10,
          average_signed_return_pct: 0.2,
        },
      ],
    };
    const withoutSectionKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          judgement_review: {
            label: "昨日判断复盘",
            rows: [{ ...holdingPeriodRow, key: "real_review" }],
          },
        },
      },
    });
    const withoutRowKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          judgement_review: {
            key: "judgement_review",
            label: "昨日判断复盘",
            rows: [
              { ...holdingPeriodRow, label: "无身份复盘" },
              { ...holdingPeriodRow, key: "real_review" },
            ],
          },
        },
      },
    });

    expect(buildMacroDecisionConsole(withoutSectionKey).judgementReview).toBeNull();

    const consoleModel = buildMacroDecisionConsole(withoutRowKey);
    expect(consoleModel.judgementReview?.rows.map((item) => item.key)).toEqual(["real_review"]);
    expect(JSON.stringify(consoleModel)).not.toContain("judgement-review:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无身份复盘");
  });

  it("formats overview data credibility as source-backed core rows", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.dataCredibility).toEqual({
      issueLabel: "2 issue(s)",
      key: "data_credibility",
      label: "数据可信度层",
      rows: [
        {
          asOf: "2026-05-20",
          key: "asset:spx",
          label: "SPX",
          qualityLabel: "可用",
          source: "FRED",
          value: "5312.40 点",
        },
        {
          asOf: "2026-05-20",
          key: "fx:dxy",
          label: "DXY",
          qualityLabel: "可用",
          source: "FRED",
          value: "104.20 点",
        },
        {
          asOf: "2026-05-20",
          key: "crypto:btc",
          label: "BTC",
          qualityLabel: "可用",
          source: "Yahoo",
          value: "110000.00 美元",
        },
        {
          asOf: "2026-05-20",
          key: "commodity:wti_futures",
          label: "CL=F",
          qualityLabel: "可用",
          source: "Yahoo",
          value: "72.40 美元",
        },
        {
          asOf: "2026-05-20",
          key: "rates:dgs10",
          label: "10Y",
          qualityLabel: "可用",
          source: "FRED",
          value: "4.70 %",
        },
        {
          asOf: "2026-05-20",
          key: "vol:vix",
          label: "VIX",
          qualityLabel: "可用",
          source: "FRED",
          value: "17.20 点",
        },
        {
          asOf: "2026-05-17",
          key: "credit:hy_oas",
          label: "HY OAS",
          qualityLabel: "过期",
          source: "FRED",
          value: "2.80 %",
        },
        {
          asOf: "2026-05-20",
          key: "liquidity:on_rrp",
          label: "ON RRP",
          qualityLabel: "降级",
          source: "FRED",
          value: "127.00 百万美元",
        },
      ],
    });
    expect(JSON.stringify(consoleModel.dataCredibility)).not.toContain("series_key");
  });

  it("does not expose raw data credibility observed dates without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          data_credibility: {
            key: "data_credibility",
            label: "数据可信度层",
            rows: [
              {
                concept_key: "asset:spx",
                display_value: "5312.40",
                label: "SPX",
                observed_at: "2026-06-10",
                quality_label: "可用",
                source_label: "FRED",
                unit_label: "点",
              },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.dataCredibility?.rows).toHaveLength(1);
    expect(consoleModel.dataCredibility?.rows[0]?.asOf).toBeNull();
    expect(JSON.stringify(consoleModel.dataCredibility)).not.toContain("2026-06-10");
  });

  it("drops data credibility sections and rows without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const credibilityRow = {
      label: "SPX",
      display_value: "5312.40",
      unit_label: "点",
      observed_at: "2026-05-20",
      source_label: "FRED",
      quality_label: "可用",
    };
    const withoutSectionKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          data_credibility: {
            label: "数据可信度层",
            rows: [{ ...credibilityRow, concept_key: "asset:spx" }],
          },
        },
      },
    });
    const withoutRowKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          data_credibility: {
            key: "data_credibility",
            label: "数据可信度层",
            rows: [
              { ...credibilityRow, label: "无身份可信度行" },
              { ...credibilityRow, concept_key: "asset:spx" },
            ],
          },
        },
      },
    });

    expect(buildMacroDecisionConsole(withoutSectionKey).dataCredibility).toBeNull();

    const consoleModel = buildMacroDecisionConsole(withoutRowKey);
    expect(consoleModel.dataCredibility?.rows.map((item) => item.key)).toEqual(["asset:spx"]);
    expect(JSON.stringify(consoleModel)).not.toContain("data-credibility:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无身份可信度行");
  });

  it("keeps every retained structured-analysis domain in the overview model", () => {
    const baseModule = macroOverviewModuleFixture();
    const retainedRows = [
      ["market_thesis", "市场主线"],
      ["fed_communication", "美联储沟通"],
      ["assets", "大类资产"],
      ["rates", "利率曲线"],
      ["policy", "美联储"],
      ["liquidity", "流动性"],
      ["growth", "经济增长"],
      ["employment", "就业"],
      ["inflation", "通胀"],
      ["volatility", "波动率"],
      ["credit", "信用市场"],
    ].map(([key, label], index) => ({
      evidence: [`${label} evidence`],
      fact: `${label} fact`,
      invalidation: `${label} invalidation`,
      key,
      label,
      regime_label: `状态 ${index + 1}`,
      trade: `${label} trade`,
    }));
    const analysis = buildMacroStructuredAnalysis(
      macroOverviewModuleFixture({
        module_read: {
          ...baseModule.module_read,
          structured_analysis: {
            key: "structured_analysis",
            label: "跨域判断链",
            rows: retainedRows,
          },
        },
      }),
    );

    expect(analysis?.rows.map((row) => row.key)).toEqual([
      "market_thesis",
      "fed_communication",
      "assets",
      "rates",
      "policy",
      "liquidity",
      "growth",
      "employment",
      "inflation",
      "volatility",
      "credit",
    ]);
    expect(analysis?.rows).toHaveLength(retainedRows.length);
  });

  it("drops structured-analysis sections and rows without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const analysisRow = {
      evidence: ["真实证据"],
      fact: "真实事实",
      invalidation: "真实失效条件",
      label: "真实判断链",
      trade: "真实交易含义",
    };
    const withoutSectionKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        structured_analysis: {
          label: "跨域判断链",
          rows: [{ ...analysisRow, key: "real_chain" }],
        },
      },
    });
    const withoutRowKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        structured_analysis: {
          key: "structured_analysis",
          label: "跨域判断链",
          rows: [
            { ...analysisRow, label: "无身份判断链" },
            { ...analysisRow, key: "real_chain" },
          ],
        },
      },
    });

    expect(buildMacroStructuredAnalysis(withoutSectionKey)).toBeNull();

    const analysis = buildMacroStructuredAnalysis(withoutRowKey);
    expect(analysis?.rows.map((row) => row.key)).toEqual(["real_chain"]);
    expect(JSON.stringify(analysis)).not.toContain("structured-analysis:0");
    expect(JSON.stringify(analysis)).not.toContain("无身份判断链");
  });

  it("formats volatility diagnostics as term-structure labels", () => {
    const diagnostics = buildMacroVolatilityDiagnostics(macroVolatilityVixModuleFixture());

    expect(diagnostics?.headline).toBe("波动率诊断 · 期限 Contango");
    expect(diagnostics?.summary).toBe(
      "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "16.9 · 1w -2.1 · 1m -4.1",
      "0.4pts · 1w +1.4pts · 1m +1.4pts",
      "1.1pts · 1w +1.6pts · 1m +2.1pts",
      "6.9pts · 1w +1.7pts · 1m +2.9pts",
      "88 · 1w +2 · 1m +4",
      "144 · 1w +2.8 · 1m +5.8",
      "0.62x · 1w -6.7% · 1m -6.7%",
      "20.5 · 1w -1.5 · 1m -4.5",
    ]);
    expect(diagnostics?.implications).toContain(
      "波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("vol:vix");
  });

  it("drops signal diagnostics with missing backend labels instead of using frontend fallback headings", () => {
    const baseModule = macroVolatilityVixModuleFixture();
    const volatilityDiagnostics = baseModule.module_read.volatility_diagnostics as Record<
      string,
      unknown
    >;
    const unlabeledDiagnostics = { ...volatilityDiagnostics };
    delete unlabeledDiagnostics.label;
    const module = {
      ...baseModule,
      module_read: {
        ...baseModule.module_read,
        volatility_diagnostics: unlabeledDiagnostics,
      },
    };

    expect(buildMacroVolatilityDiagnostics(module)).toBeNull();
  });

  it("drops signal diagnostics rows with missing backend keys instead of synthetic row ids", () => {
    const baseModule = macroVolatilityVixModuleFixture();
    const volatilityDiagnostics = baseModule.module_read.volatility_diagnostics as Record<
      string,
      unknown
    >;
    const rows = [...(volatilityDiagnostics.rows as Array<Record<string, unknown>>)];
    const firstRowWithoutKey = { ...rows[0] };
    delete firstRowWithoutKey.key;
    const module = {
      ...baseModule,
      module_read: {
        ...baseModule.module_read,
        volatility_diagnostics: {
          ...volatilityDiagnostics,
          rows: [firstRowWithoutKey, ...rows.slice(1)],
        },
      },
    };

    const diagnostics = buildMacroVolatilityDiagnostics(module);

    expect(diagnostics?.rows.map((row) => row.key)).not.toContain("volatility_diagnostics:0");
    expect(diagnostics?.rows.map((row) => row.key)).not.toContain("vix_spot");
    expect(diagnostics?.rows).toHaveLength(7);
  });

  it("formats credit stress diagnostics as decision-ready labels", () => {
    const diagnostics = buildMacroCreditDiagnostics(macroCreditStressModuleFixture());

    expect(diagnostics?.headline).toBe("信用压力诊断 · 尾部走阔");
    expect(diagnostics?.summary).toBe(
      "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
    );
    expect(diagnostics?.rows.map((row) => row.value)).toEqual([
      "420bp · 1w +30bp · 1m +50bp · 3m +70bp",
      "120bp · 1w +10bp · 1m +15bp · 3m +20bp",
      "530bp · 1w +90bp · 1m +100bp · 3m +160bp",
      "HYG 1w -1.3% · LQD 1w +0.9% · 相对 -2.2%",
      "-0.1 · 1w +0.2 · 1m +0.3 · 3m +0.5",
      "30% · 1q +12%",
    ]);
    expect(diagnostics?.implications).toContain(
      "信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。",
    );
    expect(diagnostics?.invalidations).toContain(
      "若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。",
    );
    expect(JSON.stringify(diagnostics)).not.toContain("credit:hy_oas");
  });

  it("formats crypto derivatives OI rows as source-backed asset diagnostics", () => {
    const module = macroOverviewModuleFixture({
      module_read: {
        asset_class_diagnostics: {
          label: "加密 beta 诊断",
          regime_label: "加密杠杆追涨",
          summary: "加密价格、OI、资金费率和基差同步走热，DVOL 升温。",
          rows: [
            {
              key: "btc_perp_oi",
              label: "BTC 永续 OI",
              current_bn: 16.5,
              change_1w_pct: 10,
              status_label: "杠杆扩张",
            },
          ],
          implications: ["降低杠杆和追价。"],
          invalidations: ["若 OI 收缩且 funding/basis 回落，读法降级。"],
        },
      },
    });

    const diagnostics = buildMacroAssetClassDiagnostics(module);

    expect(diagnostics?.headline).toBe("加密 beta 诊断 · 加密杠杆追涨");
    expect(diagnostics?.rows).toEqual([
      {
        key: "btc_perp_oi",
        label: "BTC 永续 OI",
        statusLabel: "杠杆扩张",
        value: "$16.5B · 1w +10%",
      },
    ]);
  });

  it("uses source-backed top-change metadata instead of section labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            {
              code: "rrp_buffer_low",
              label: "RRP 缓冲偏低",
              description: "ON RRP buffer is below 300bn USD",
              evidence_label: "ON RRP buffer is below 300bn USD",
              change_label: "ON RRP -$40B",
              value_label: "最新 $280B",
              source_label: "NY Fed",
              observed_at: "2026-06-16",
              node: "funding",
              node_label: "资金面",
              severity_label: "高",
              kind: "trigger",
            },
            {
              code: "feature_change",
              label: "跨资产变化",
              description: "Cross-asset confirmation shifted",
              evidence_label: "Cross-asset confirmation shifted",
              node: "cross_asset",
              node_label: "跨资产确认",
              kind: "trigger",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.topChanges.map((item) => item.meta)).toEqual([
      "ON RRP -$40B · 最新 $280B · NY Fed · 2026-06-16 · 高",
      null,
    ]);
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("资金面");
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("跨资产确认");
  });

  it("does not infer decision-console section labels from node or kind codes", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "node_code_without_label",
            label: "缺 node label 的确认",
            description: "Known node code must not become display text.",
            evidence_label: "Known node code must not become display text.",
            node: "funding",
          },
        ],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            {
              code: "node_label_present",
              label: "显式 section label",
              description: "Explicit backend node label is displayable.",
              evidence_label: "Explicit backend node label is displayable.",
              node: "funding",
              node_label: "资金面",
              kind: "trigger",
            },
            {
              code: "node_code_without_label",
              label: "缺 node label 的变化",
              description: "Known node and kind codes must not become display text.",
              evidence_label: "Known node and kind codes must not become display text.",
              node: "funding",
              kind: "trigger",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations[0].meta).toBeNull();
    expect(consoleModel.topChanges.map((item) => item.meta)).toEqual([null, null]);
    expect(JSON.stringify(consoleModel.confirmations)).not.toContain("资金面");
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("资金面");
    expect(JSON.stringify(consoleModel.topChanges[1])).not.toContain("资金面");
    expect(JSON.stringify(consoleModel.topChanges[1])).not.toContain("funding");
    expect(JSON.stringify(consoleModel.topChanges[1])).not.toContain("触发");
  });

  it("does not use module evidence node labels as meta fallbacks", () => {
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "confirmation_with_explicit_meta",
            label: "显式元信息确认",
            evidence_label: "确认细节",
            meta: "后端显式 meta",
            node_label: "资金面",
          },
          {
            code: "confirmation_with_node_label_only",
            label: "只有节点标签的确认",
            evidence_label: "确认细节",
            node_label: "跨资产确认",
          },
        ],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations.map((item) => item.meta)).toEqual(["后端显式 meta", null]);
    expect(JSON.stringify(consoleModel.confirmations[1])).not.toContain("跨资产确认");
  });

  it("drops sparse decision-console items instead of creating placeholder details", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "real_confirmation",
            label: "真实确认",
            description: "资金面确认风险偏好。",
            evidence_label: "资金面确认风险偏好。",
          },
          { label: "空确认" },
        ],
        contradictions: [{ label: "空反证" }],
        watch_triggers: [],
        invalidations: [],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            {
              code: "rrp_down",
              label: "真实变化",
              description: "RRP 继续下行。",
              evidence_label: "RRP 继续下行。",
            },
            { code: "empty_change", label: "空变化" },
          ],
          quality_blockers: [
            {
              code: "missing_stfm",
              label: "真实阻断",
              description: "legacy quality description must stay internal.",
              evidence_label: "缺少 OFR STFM 确认。",
            },
            {
              code: "description_only_blocker",
              label: "旧阻断",
              description: "Legacy quality-only description must stay internal.",
            },
            { code: "empty_blocker", label: "空阻断" },
          ],
          watchlist_alerts: {
            key: "watchlist_alerts",
            label: "Watchlist",
            rules: [
              {
                key: "watch:spx_breaks_prior_low",
                label: "真实规则",
                detail: "SPX 跌破上周低点。",
              },
              { label: "空规则" },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations.map((item) => item.label)).toEqual(["真实确认"]);
    expect(consoleModel.contradictions).toEqual([]);
    expect(consoleModel.topChanges.map((item) => item.label)).toEqual(["真实变化"]);
    expect(consoleModel.qualityBlockers.map((item) => item.label)).toEqual(["真实阻断"]);
    expect(consoleModel.watchlistAlerts?.rules.map((item) => item.label)).toEqual(["真实规则"]);
    expect(JSON.stringify(consoleModel)).not.toContain("暂无");
    expect(JSON.stringify(consoleModel)).not.toContain(
      "legacy quality description must stay internal",
    );
    expect(JSON.stringify(consoleModel)).not.toContain(
      "Legacy quality-only description must stay internal",
    );
  });

  it("does not expose decision evidence descriptions without evidence labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "legacy_confirmation",
            label: "旧确认",
            description: "legacy confirmation description",
          },
        ],
        contradictions: [
          {
            code: "legacy_contradiction",
            label: "旧反证",
            description: "legacy contradiction description",
          },
        ],
        watch_triggers: [],
        invalidations: [],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            {
              code: "legacy_top_change",
              label: "旧变化",
              description: "legacy top-change description",
              kind: "trigger",
              node_label: "资金面",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations).toEqual([]);
    expect(consoleModel.contradictions).toEqual([]);
    expect(consoleModel.topChanges).toEqual([]);
    expect(JSON.stringify(consoleModel)).not.toContain("legacy confirmation description");
    expect(JSON.stringify(consoleModel)).not.toContain("legacy contradiction description");
    expect(JSON.stringify(consoleModel)).not.toContain("legacy top-change description");
  });

  it("drops decision-console top changes and blockers without backend codes", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            { label: "无代码变化", description: "Should not keep a synthetic key." },
            {
              code: "real_change",
              label: "真实变化",
              description: "Uses backend identity.",
              evidence_label: "Uses backend identity.",
            },
          ],
          quality_blockers: [
            { label: "无代码阻断", description: "Should not keep a synthetic key." },
            {
              code: "real_blocker",
              label: "真实阻断",
              description: "legacy blocker description must stay internal.",
              evidence_label: "Uses backend identity.",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.topChanges.map((item) => item.key)).toEqual(["real_change"]);
    expect(consoleModel.qualityBlockers.map((item) => item.key)).toEqual(["real_blocker"]);
    expect(JSON.stringify(consoleModel)).not.toContain("top:0");
    expect(JSON.stringify(consoleModel)).not.toContain("quality:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无代码");
    expect(JSON.stringify(consoleModel)).not.toContain(
      "legacy blocker description must stay internal",
    );
  });

  it("drops decision-console confirmations and contradictions without backend codes", () => {
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          { label: "无代码确认", description: "Should not keep a synthetic key." },
          {
            code: "real_confirmation",
            label: "真实确认",
            description: "Uses backend identity.",
            evidence_label: "Uses backend identity.",
          },
        ],
        contradictions: [
          { label: "无代码反证", description: "Should not keep a synthetic key." },
          {
            code: "real_contradiction",
            label: "真实反证",
            description: "Uses backend identity.",
            evidence_label: "Uses backend identity.",
          },
        ],
        watch_triggers: [],
        invalidations: [],
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations.map((item) => item.key)).toEqual(["real_confirmation"]);
    expect(consoleModel.contradictions.map((item) => item.key)).toEqual(["real_contradiction"]);
    expect(JSON.stringify(consoleModel)).not.toContain("confirm:0");
    expect(JSON.stringify(consoleModel)).not.toContain("contradict:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无代码");
  });

  it("formats market event flow as a source-backed event stream", () => {
    const eventFlow = buildMacroMarketEventFlow(macroOverviewModuleFixture());

    expect(eventFlow).toEqual({
      key: "market_event_flow",
      label: "市场事件流",
      rows: [
        {
          categoryLabel: "美联储",
          date: "2026-06-10",
          detail: "油价与美元走强，风险资产低开。",
          impactLabel: "不改主线",
          key: "news:news-row-1",
          label: "中东震荡下，日本追加预算预期升温",
          meta: "bloomberg.com · 美联储 · 不改主线 · 近期",
          severityLabel: "低",
          sourceUrl: "https://news.google.com/articles/macro-1",
          watch: "SPX · 美元 · 美联储",
        },
        {
          categoryLabel: "政策",
          date: "2026-06-17",
          detail: "2026-06-17 · 还有 1 天 · 14:00 ET",
          impactLabel: "政策路径",
          key: "official_calendar:fomc_decision_next",
          label: "FOMC 决议",
          meta: "官方日历 · 政策 · 政策路径 · 0-3天",
          severityLabel: "高",
          sourceUrl: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
          watch: "利率路径和流动性定价。",
        },
        {
          categoryLabel: "国债供给",
          date: "2026-06-23",
          detail: "2026-06-23 · 还有 7 天 · 2026-06-18 公告 · 2026-06-30 交割",
          impactLabel: "拍卖/交割",
          key: "treasury_auction:2y_next_auction_days",
          label: "2Y 国债拍卖日历",
          meta: "US Treasury · 国债供给 · 拍卖/交割 · 4-7天",
          severityLabel: "中",
          sourceUrl: "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
          watch: "关注拍卖需求、公告规模和交割日资金占用。",
        },
        {
          categoryLabel: "国债供给",
          date: "2026-06-10",
          detail: "2026-06-10 · 2.52 · CUSIP 91282CQQ9",
          impactLabel: "拍卖结果",
          key: "treasury_auction:10y_bid_to_cover",
          label: "10Y 国债拍卖 Bid/Cover",
          meta: "US Treasury · 国债供给 · 拍卖结果 · 近期",
          severityLabel: "中",
          sourceUrl:
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
          watch: "拍卖结果作为国债需求和期限溢价压力证据。",
        },
        {
          categoryLabel: "政策",
          date: "2026-05-08",
          detail: "2026-05-08 · Waller, Update On Federal Reserve Bank Operations",
          impactLabel: "Fed 沟通",
          key: "official_fed_text:speech_latest",
          label: "Fed 官员讲话",
          meta: "Federal Reserve · 政策 · Fed 沟通 · 近期",
          severityLabel: "中",
          sourceUrl: "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
          watch: "跟踪措辞、投票分歧和政策路径信号。",
        },
      ],
    });
  });

  it("drops market event flow with missing backend identity metadata", () => {
    const baseModule = macroOverviewModuleFixture();
    const marketEventFlow = baseModule.module_read.market_event_flow as Record<string, unknown>;
    const flowWithoutLabel = { ...marketEventFlow };
    delete flowWithoutLabel.label;
    const flowWithoutKey = { ...marketEventFlow };
    delete flowWithoutKey.key;

    expect(
      buildMacroMarketEventFlow({
        ...baseModule,
        module_read: { ...baseModule.module_read, market_event_flow: flowWithoutLabel },
      }),
    ).toBeNull();
    expect(
      buildMacroMarketEventFlow({
        ...baseModule,
        module_read: { ...baseModule.module_read, market_event_flow: flowWithoutKey },
      }),
    ).toBeNull();
  });

  it("does not expose raw market event flow windows without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const marketEventFlow = baseModule.module_read.market_event_flow as Record<string, unknown>;
    const eventFlow = buildMacroMarketEventFlow({
      ...baseModule,
      module_read: {
        ...baseModule.module_read,
        market_event_flow: {
          ...marketEventFlow,
          rows: [
            {
              key: "event:raw_window",
              label: "裸窗口事件",
              date: "2026-06-22",
              detail: "Raw market event windows must stay internal.",
              watch: "Track explicit labels only.",
              source: "官方日历",
              category_label: "政策",
              impact_label: "政策路径",
              window: "raw-window-0-3d",
              severity_label: "高",
            },
          ],
        },
      },
    });

    expect(eventFlow?.rows).toEqual([
      {
        categoryLabel: "政策",
        date: "2026-06-22",
        detail: "Raw market event windows must stay internal.",
        impactLabel: "政策路径",
        key: "event:raw_window",
        label: "裸窗口事件",
        meta: "官方日历 · 政策 · 政策路径",
        severityLabel: "高",
        sourceUrl: null,
        watch: "Track explicit labels only.",
      },
    ]);
    expect(JSON.stringify(eventFlow?.rows)).not.toContain("raw-window-0-3d");
  });

  it("drops market event flow rows with missing backend keys instead of synthetic row ids", () => {
    const baseModule = macroOverviewModuleFixture();
    const marketEventFlow = baseModule.module_read.market_event_flow as Record<string, unknown>;
    const rows = [...(marketEventFlow.rows as Array<Record<string, unknown>>)];
    const firstRowWithoutKey = { ...rows[0] };
    delete firstRowWithoutKey.key;
    const eventFlow = buildMacroMarketEventFlow({
      ...baseModule,
      module_read: {
        ...baseModule.module_read,
        market_event_flow: {
          ...marketEventFlow,
          rows: [firstRowWithoutKey, ...rows.slice(1)],
        },
      },
    });

    expect(eventFlow?.rows.map((row) => row.key)).not.toContain("market-event:0");
    expect(eventFlow?.rows.map((row) => row.key)).not.toContain("news:news-row-1");
    expect(eventFlow?.rows).toHaveLength(4);
  });

  it("formats watchlist alerts from the backend decision-console payload", () => {
    const consoleModel = buildMacroDecisionConsole(macroOverviewModuleFixture());

    expect(consoleModel.watchlistAlerts).toEqual({
      assets: [
        { action: "做多/防守", key: "BIL", label: "现金/短债", symbol: "BIL" },
        { action: "回避/做空代理", key: "QQQ", label: "纳斯达克", symbol: "QQQ" },
        { action: "低配", key: "HYG", label: "高收益信用", symbol: "HYG" },
      ],
      key: "watchlist_alerts",
      label: "Watchlist 与触发提醒",
      rules: [
        {
          detail: "10Y real yield keeps rising.",
          key: "watch:real_yield_breakout",
          label: "实际利率突破",
          meta: "触发 · 24h · 高",
        },
        {
          detail: "10Y yield loses pressure.",
          key: "invalidation:ten_year_yield_reverses",
          label: "10年期收益率回落",
          meta: "失效",
        },
        {
          detail: "检查对应 provider 导入与最新观测。",
          key: "quality:missing_asset_spy",
          label: "缺少当前数据：SPY",
          meta: "质量 · 阻断",
        },
      ],
    });
  });

  it("does not expose watchlist asset symbols as labels without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          watchlist_alerts: {
            key: "watchlist_alerts",
            label: "Watchlist 与触发提醒",
            assets: [
              {
                action: "Do not show symbol-only rows",
                key: "symbol_only_asset",
                symbol: "RAW_SYMBOL_ONLY",
              },
              { action: "做多/防守", key: "BIL", label: "现金/短债", symbol: "BIL" },
            ],
            rules: [],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.watchlistAlerts?.assets).toEqual([
      { action: "做多/防守", key: "BIL", label: "现金/短债", symbol: "BIL" },
    ]);
    expect(JSON.stringify(consoleModel.watchlistAlerts?.assets)).not.toContain("RAW_SYMBOL_ONLY");
    expect(JSON.stringify(consoleModel.watchlistAlerts?.assets)).not.toContain(
      "Do not show symbol-only rows",
    );
  });

  it("drops watchlist alert sections and rows without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const asset = { symbol: "BIL", label: "现金/短债", action: "做多/防守" };
    const rule = {
      label: "实际利率突破",
      detail: "10Y real yield keeps rising.",
      kind: "watch",
      kind_label: "触发",
      window: "24h",
      severity: "high",
      severity_label: "高",
    };
    const withoutSectionKey = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          watchlist_alerts: {
            label: "Watchlist 与触发提醒",
            assets: [{ ...asset, key: "BIL" }],
            rules: [{ ...rule, key: "watch:real_yield_breakout" }],
          },
        },
      },
    });
    const withoutRowKeys = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          watchlist_alerts: {
            key: "watchlist_alerts",
            label: "Watchlist 与触发提醒",
            assets: [asset, { ...asset, key: "BIL", label: "现金/短债" }],
            rules: [
              rule,
              {
                key: "legacy_description_watch_rule",
                label: "旧正文规则",
                description: "Legacy watchlist rule description must stay internal.",
                kind_label: "触发",
              },
              {
                ...rule,
                code: "legacy_code_watch_rule",
                label: "旧规则",
                detail: "Legacy code-only rule must stay internal.",
              },
              { ...rule, key: "watch:real_yield_breakout" },
            ],
          },
        },
      },
    });

    expect(buildMacroDecisionConsole(withoutSectionKey).watchlistAlerts).toBeNull();

    const consoleModel = buildMacroDecisionConsole(withoutRowKeys);
    expect(consoleModel.watchlistAlerts?.assets.map((item) => item.key)).toEqual(["BIL"]);
    expect(consoleModel.watchlistAlerts?.rules.map((item) => item.key)).toEqual([
      "watch:real_yield_breakout",
    ]);
    expect(JSON.stringify(consoleModel)).not.toContain("watchlist-asset:0");
    expect(JSON.stringify(consoleModel)).not.toContain("watchlist-rule:0");
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain(
      "legacy_description_watch_rule",
    );
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain(
      "Legacy watchlist rule description must stay internal",
    );
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain(
      "legacy_code_watch_rule",
    );
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain("旧规则");
  });

  it("does not infer watchlist rule kind labels from kind", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          watchlist_alerts: {
            key: "watchlist_alerts",
            label: "Watchlist 与触发提醒",
            rules: [
              {
                key: "watch:real_yield_breakout",
                label: "实际利率突破",
                detail: "10Y real yield keeps rising.",
                kind: "watch",
                window: "24h",
                severity_label: "高",
              },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.watchlistAlerts?.rules[0].meta).toBe("高");
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain("触发");
  });

  it("does not expose raw watchlist rule windows without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          watchlist_alerts: {
            key: "watchlist_alerts",
            label: "Watchlist 与触发提醒",
            assets: [],
            rules: [
              {
                key: "watch:raw_window",
                label: "裸窗口规则",
                detail: "Raw watchlist windows must stay internal.",
                kind_label: "触发",
                window: "raw-window-24h",
                severity_label: "高",
              },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.watchlistAlerts?.rules).toEqual([
      {
        detail: "Raw watchlist windows must stay internal.",
        key: "watch:raw_window",
        label: "裸窗口规则",
        meta: "触发 · 高",
      },
    ]);
    expect(JSON.stringify(consoleModel.watchlistAlerts?.rules)).not.toContain("raw-window-24h");
  });

  it("does not expose raw decision-console time windows without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "raw_window_confirmation",
            label: "裸窗口确认",
            evidence_label: "确认细节",
            time_window: "raw-window-confirmation",
            severity_label: "高",
          },
        ],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          scenario_cases: [
            {
              case: "base",
              label: "基准情景",
              probability_label: "50%",
              time_window: "raw-window-scenario",
              thesis: "资金压力维持，信用 beta 继续承压。",
              trade: "防守：做多/持有 BIL，低配 QQQ 与 HYG。",
              entry_condition: "SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
              stop: "SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
              invalidation: "若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
            },
          ],
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              time_window: "raw-window-trade",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations[0]?.meta).toBe("高");
    expect(consoleModel.scenarioCases[0]?.meta).toBe("50%");
    expect(consoleModel.tradeMap[0]?.window).toBeNull();
    expect(JSON.stringify(consoleModel)).not.toContain("raw-window-confirmation");
    expect(JSON.stringify(consoleModel)).not.toContain("raw-window-scenario");
    expect(JSON.stringify(consoleModel)).not.toContain("raw-window-trade");
  });

  it("formats scenario cases from backend decision-console payload", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          scenario_cases: [
            {
              case: "base",
              label: "基准情景",
              probability_label: "50%",
              time_window: "未来 2 周",
              time_window_label: "未来 2 周",
              thesis: "资金压力维持，信用 beta 继续承压。",
              trade: "防守：做多/持有 BIL，低配 QQQ 与 HYG。",
              entry_condition: "SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
              stop: "SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
              invalidation: "若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.scenarioCases).toEqual([
      {
        detail: "资金压力维持，信用 beta 继续承压。",
        entry: "入场：SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
        invalidation: "失效：若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
        key: "base",
        label: "基准情景",
        meta: "50% · 未来 2 周",
        stop: "止损：SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
        trade: "交易：防守：做多/持有 BIL，低配 QQQ 与 HYG。",
      },
    ]);
  });

  it("drops scenario cases and trade-map rows without backend identity", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const scenario = {
      label: "无身份情景",
      thesis: "Should not keep a synthetic key.",
      trade: "降低高 beta 暴露。",
      entry_condition: "SOFR-IORB 仍为正。",
      stop: "SOFR 回到 IORB 附近。",
      invalidation: "信用利差收窄。",
    };
    const tradeMap = {
      label: "无表达式交易映射",
      legs: [{ symbol: "BIL", label: "现金/短债", action: "做多/防守" }],
    };
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          scenario_cases: [
            scenario,
            {
              ...scenario,
              case: "base",
              label: "基准情景",
            },
          ],
          trade_map: [
            tradeMap,
            {
              ...tradeMap,
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.scenarioCases.map((item) => item.key)).toEqual(["base"]);
    expect(consoleModel.tradeMap.map((item) => item.key)).toEqual(["risk_down_credit_sensitive"]);
    expect(JSON.stringify(consoleModel)).not.toContain("scenario:0");
    expect(JSON.stringify(consoleModel)).not.toContain("trade:0");
    expect(JSON.stringify(consoleModel)).not.toContain("无身份情景");
    expect(JSON.stringify(consoleModel)).not.toContain("无表达式交易映射");
  });

  it("omits unknown decision-console metadata instead of fallback placeholder labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          scenario_cases: [
            {
              case: "base",
              label: "基准情景",
              thesis: "资金压力维持。",
              trade: "降低高 beta 暴露。",
              entry_condition: "SOFR-IORB 仍为正。",
              stop: "SOFR 回到 IORB 附近。",
              invalidation: "信用利差收窄。",
            },
          ],
          top_changes: [
            {
              code: "unmapped_signal_code",
              description: "This row should be dropped without a display label.",
              node: "funding",
            },
          ],
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              legs: [{ symbol: "BIL", label: "现金/短债", action: "做多/防守" }],
            },
            {
              expression: "unmapped_trade_expression",
              legs: [{ symbol: "QQQ", label: "纳斯达克", action: "回避" }],
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.scenarioCases[0].meta).toBeNull();
    expect(consoleModel.topChanges).toEqual([]);
    expect(consoleModel.tradeMap).toHaveLength(1);
    expect(consoleModel.tradeMap[0]).toMatchObject({
      label: "风险降档 / 信用敏感",
      window: null,
    });
    expect(consoleModel.tradeMap[0]).not.toHaveProperty("confirms");
    expect(consoleModel.tradeMap[0]).not.toHaveProperty("invalidates");
    expect(JSON.stringify(consoleModel)).not.toContain("待确认");
    expect(JSON.stringify(consoleModel)).not.toContain("unmapped_signal_code");
    expect(JSON.stringify(consoleModel)).not.toContain("unmapped_trade_expression");
  });

  it("drops known scenario signals without backend display labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        ...baseModule.module_evidence,
        confirmations: [
          {
            code: "sofr_above_iorb",
            description: "Known code without backend label must be dropped.",
          },
        ],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          top_changes: [
            {
              code: "hy_oas_stress",
              description: "Known code without backend label must be dropped.",
              kind: "trigger",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations).toEqual([]);
    expect(consoleModel.topChanges).toEqual([]);
    expect(JSON.stringify(consoleModel.confirmations)).not.toContain("SOFR 高于 IORB");
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("高收益债利差压力");
  });

  it("drops trade-map rows without backend display labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              legs: [{ symbol: "BIL", label: "现金/短债", action: "做多/防守" }],
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.tradeMap).toEqual([]);
    expect(JSON.stringify(consoleModel.tradeMap)).not.toContain("风险降档 / 信用敏感");
  });

  it("drops trade-map checklist rows without backend kind labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              action_checklist: [
                {
                  kind: "confirm",
                  label: "信用压力确认",
                  description: "缺少 kind_label 时不展示。",
                },
              ],
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.tradeMap[0].checklist).toEqual([]);
    expect(JSON.stringify(consoleModel.tradeMap[0].checklist)).not.toContain("确认");
  });

  it("drops trade-map historical rows without backend outcome labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              historical_review: {
                label: "五资产 60日验证",
                win_rate_label: "1/1",
                average_return_pct: -6,
                max_adverse_excursion_pct: 0,
                rows: [
                  {
                    asset: "NDX",
                    label: "纳斯达克",
                    return_pct: -6,
                    outcome: "hit",
                  },
                ],
              },
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.tradeMap[0].history).toEqual([
      "五资产 60日验证 · 胜率 1/1 · 均值 -6.00% · 最大逆风 0.00%",
    ]);
    expect(JSON.stringify(consoleModel.tradeMap[0].history)).not.toContain("命中");
    expect(JSON.stringify(consoleModel.tradeMap[0].history)).not.toContain("未中");
  });

  it("does not infer future catalyst source labels from event kind", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          future_catalysts: {
            key: "future_catalysts",
            label: "未来 24/72h 催化剂",
            rows: [
              {
                key: "event:calendar_without_source",
                label: "缺来源日历事件",
                detail: "Missing source must stay missing.",
                kind: "calendar",
                window_label: "24h",
                severity_label: "高",
              },
            ],
          },
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.futureCatalysts[0].meta).toBe("24h · 高");
    expect(JSON.stringify(consoleModel.futureCatalysts)).not.toContain("官方日历");
  });

  it("formats trade-map historical review from backend evidence", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              time_window: "1w",
              time_window_label: "1周",
              historical_review: {
                label: "五资产 60日验证",
                window: "60d",
                sample_count: 5,
                hit_count: 4,
                win_rate: 0.8,
                win_rate_label: "4/5",
                average_return_pct: -2.6,
                max_adverse_excursion_pct: -4,
                rows: [
                  {
                    asset: "NDX",
                    label: "纳斯达克",
                    return_pct: -6,
                    outcome: "hit",
                    outcome_label: "命中",
                  },
                  {
                    asset: "TLT",
                    label: "长债",
                    return_pct: 1,
                    outcome: "hit",
                    outcome_label: "命中",
                  },
                ],
              },
              portfolio_review: {
                label: "$10K 纸面映射",
                notional_usd: 10000,
                deployed_usd: 10000,
                pnl_usd: 460,
                pnl_pct: 4.6,
                max_adverse_usd: -80,
                risk_temperature: "低",
                summary: "$10,000 · P&L +$460 · 胜率 4/5",
              },
              action_checklist: [
                {
                  kind: "confirm",
                  kind_label: "确认",
                  label: "HY OAS 5日走阔",
                  description: "观察 HY OAS 5日走阔 是否继续确认。",
                },
                {
                  kind: "position_review",
                  kind_label: "纸面仓位",
                  label: "纸面仓位复盘",
                  description: "$10,000 · P&L +$460 · 胜率 4/5",
                },
              ],
              historical_trust: {
                label: "历史可信度",
                score_pct: 73.3,
                quality: "中",
                sample_count: 15,
                hit_count: 11,
                summary: "历史可信度 73.3% · 中 · 15 个样本",
              },
              holding_period_review: {
                label: "持有期复盘",
                rows: [
                  {
                    horizon: "1d",
                    label: "1D",
                    status_label: "已完成",
                    win_rate_label: "5/5",
                    pnl_usd: 100,
                    average_signed_return_pct: 1,
                  },
                  {
                    horizon: "5d",
                    label: "5D",
                    status_label: "已完成",
                    win_rate_label: "4/5",
                    pnl_usd: 220,
                    average_signed_return_pct: 2.2,
                  },
                  {
                    horizon: "20d",
                    label: "20D",
                    status_label: "观察中",
                    win_rate_label: "2/5",
                    pnl_usd: -80,
                    average_signed_return_pct: -0.8,
                  },
                ],
              },
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.tradeMap[0].window).toBe("1周");
    expect(consoleModel.tradeMap[0]).not.toHaveProperty("confirms");
    expect(consoleModel.tradeMap[0]).not.toHaveProperty("invalidates");
    expect(consoleModel.tradeMap[0].history).toEqual([
      "五资产 60日验证 · 胜率 4/5 · 均值 -2.60% · 最大逆风 -4.00%",
      "NDX 纳斯达克 -6.00% 命中",
      "TLT 长债 +1.00% 命中",
    ]);
    expect(consoleModel.tradeMap[0].portfolio).toEqual([
      "$10K 纸面映射 · $10,000 · P&L +$460 · 胜率 4/5 · 风险温度 低",
    ]);
    expect(consoleModel.tradeMap[0].checklist).toEqual([
      "确认 · HY OAS 5日走阔 · 观察 HY OAS 5日走阔 是否继续确认。",
      "纸面仓位 · 纸面仓位复盘 · $10,000 · P&L +$460 · 胜率 4/5",
    ]);
    expect(consoleModel.tradeMap[0].trust).toEqual(["历史可信度 73.3% · 中 · 15 个样本"]);
    expect(consoleModel.tradeMap[0].holding).toEqual([
      "1D 已完成 · 5/5 · P&L +$100 · 均值 +1.00%",
      "5D 已完成 · 4/5 · P&L +$220 · 均值 +2.20%",
      "20D 观察中 · 2/5 · P&L -$80 · 均值 -0.80%",
    ]);
  });

  it("does not expose retired trade-map confirm and invalidation code lists", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              confirms_on: ["hy_oas_widening_5d"],
              invalidates_on: ["vix_returns_to_carry"],
              action_checklist: [
                {
                  kind: "confirm",
                  kind_label: "确认",
                  label: "显式信用压力确认",
                  description: "只消费 action_checklist 展示契约。",
                },
              ],
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);
    const tradeMap = consoleModel.tradeMap[0] as Record<string, unknown>;

    expect(tradeMap).not.toHaveProperty("confirms");
    expect(tradeMap).not.toHaveProperty("invalidates");
    expect(tradeMap.checklist).toEqual([
      "确认 · 显式信用压力确认 · 只消费 action_checklist 展示契约。",
    ]);
    expect(JSON.stringify(tradeMap)).not.toContain("HY OAS 5日走阔");
    expect(JSON.stringify(tradeMap)).not.toContain("VIX 回到 carry 区间");
  });

  it("drops trade-map review sections without backend labels", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              historical_review: {
                win_rate_label: "4/5",
                average_return_pct: -2.6,
                max_adverse_excursion_pct: -4,
                rows: [{ asset: "NDX", label: "纳斯达克", return_pct: -6, outcome: "hit" }],
              },
              portfolio_review: {
                summary: "$10,000 · P&L +$460 · 胜率 4/5",
                risk_temperature: "低",
              },
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.tradeMap[0].history).toEqual([]);
    expect(consoleModel.tradeMap[0].portfolio).toEqual([]);
    expect(JSON.stringify(consoleModel)).not.toContain("历史验证");
    expect(JSON.stringify(consoleModel)).not.toContain("纸面映射");
  });

  it("omits unmapped decision-console helper labels instead of generic copy", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          future_catalysts: {
            key: "future_catalysts",
            label: "未来 24/72h 催化剂",
            rows: [
              {
                key: "watch:unknown_kind",
                label: "未知类型催化剂",
                detail: "Should not get generic event/severity labels.",
                kind: "unknown_kind",
                severity: "unknown_severity",
                window: "24h",
              },
            ],
          },
          top_changes: [
            {
              code: "mapped_change",
              label: "已映射变化",
              description: "Should not get generic section/severity labels.",
              evidence_label: "Should not get generic section/severity labels.",
              kind: "unknown_kind",
              severity: "unknown_severity",
            },
          ],
          trade_map: [
            {
              expression: "risk_down_credit_sensitive",
              label: "风险降档 / 信用敏感",
              action_checklist: [
                {
                  kind: "unknown_kind",
                  label: "未知动作",
                  description: "Should be dropped without a mapped checklist kind.",
                },
                {
                  kind: "confirm",
                  kind_label: "确认",
                  label: "确认动作",
                  description: "保留已映射动作。",
                },
              ],
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.futureCatalysts[0].meta).toBeNull();
    expect(consoleModel.topChanges[0].meta).toBeNull();
    expect(consoleModel.tradeMap[0].checklist).toEqual(["确认 · 确认动作 · 保留已映射动作。"]);
    expect(JSON.stringify(consoleModel)).not.toContain("事件");
    expect(JSON.stringify(consoleModel)).not.toContain("提示");
    expect(JSON.stringify(consoleModel)).not.toContain("宏观");
    expect(JSON.stringify(consoleModel)).not.toContain("行动");
    expect(JSON.stringify(consoleModel)).not.toContain("未知动作");
  });

  it("does not infer decision-console severity labels from severity codes", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole = baseModule.module_read.decision_console as Record<string, unknown>;
    const module = macroOverviewModuleFixture({
      module_evidence: {
        confirmations: [
          {
            code: "severity_without_label",
            label: "缺 severity label 的确认",
            description: "Known severity code must not become display text.",
            evidence_label: "Known severity code must not become display text.",
            severity: "high",
          },
        ],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
      module_read: {
        ...baseModule.module_read,
        decision_console: {
          ...decisionConsole,
          future_catalysts: {
            key: "future_catalysts",
            label: "未来 24/72h 催化剂",
            rows: [
              {
                key: "watch:severity_without_label",
                label: "缺 severity label 的催化剂",
                detail: "Known severity code must not become display text.",
                window_label: "24h",
                severity: "high",
              },
            ],
          },
          top_changes: [
            {
              code: "top_change_without_severity_label",
              label: "缺 severity label 的变化",
              description: "Known severity code must not become display text.",
              evidence_label: "Known severity code must not become display text.",
              kind: "trigger",
              severity: "high",
            },
          ],
          quality_blockers: [
            {
              code: "quality_without_severity_label",
              label: "缺 severity label 的质量问题",
              description: "Known severity code must not become display text.",
              evidence_label: "Known severity code must not become display text.",
              severity: "error",
            },
          ],
        },
      },
    });

    const consoleModel = buildMacroDecisionConsole(module);

    expect(consoleModel.confirmations[0].meta).toBeNull();
    expect(consoleModel.futureCatalysts[0].meta).toBe("24h");
    expect(consoleModel.topChanges[0].meta).toBeNull();
    expect(consoleModel.qualityBlockers[0].meta).toBeNull();
    expect(JSON.stringify(consoleModel.confirmations)).not.toContain("高");
    expect(JSON.stringify(consoleModel.futureCatalysts)).not.toContain("高");
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("高");
    expect(JSON.stringify(consoleModel.topChanges)).not.toContain("触发");
    expect(JSON.stringify(consoleModel.qualityBlockers)).not.toContain("阻断");
  });
});
