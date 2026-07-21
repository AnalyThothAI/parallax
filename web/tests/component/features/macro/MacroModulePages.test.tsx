import { MacroModulePageRenderer } from "@features/macro/ui/pages/MacroModulePageRenderer";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import {
  macroAssetsModuleFixture,
  macroCreditStressModuleFixture,
  macroCorrelationFixture,
  macroEmploymentModuleFixture,
  macroGdpModuleFixture,
  macroInflationModuleFixture,
  macroLiquidityRrpTgaModuleFixture,
  macroModuleFixture,
  macroOverviewModuleFixture,
  macroSeriesFixture,
  macroVolatilityVixModuleFixture,
  macroYieldCurveModuleFixture,
} from "@tests/fixtures/macroFixture";
import { ok } from "@tests/msw/fixtures";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { apiMock, setupAppRouteTest } from "@tests/routes/routeTestSetup";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const chartMocks = vi.hoisted(() => {
  const lineSeries = { setData: vi.fn() };
  const chartApi = {
    addSeries: vi.fn(() => lineSeries),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    resize: vi.fn(),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  };
  return {
    chartApi,
    createChart: vi.fn(() => chartApi),
    lineSeries,
  };
});

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  LineSeries: "LineSeries",
  createChart: chartMocks.createChart,
}));

describe("Macro module pages", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/series") {
          const conceptKeys = String(options?.params?.concept_keys ?? "asset:spx").split(",");
          return ok(macroSeriesFixture(conceptKeys));
        }
        throw new Error(`unexpected path ${path}`);
      };
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders overview page grammar and fetches series from backend chart concepts", async () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroOverviewModuleFixture()}
        moduleId="overview"
        pageKind="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    expect(screen.getByRole("region", { name: "宏观总览模块页面" })).toHaveAttribute(
      "data-page-kind",
      "overview",
    );
    expect(document.querySelector(".macro-page-panel-current")).not.toBeInTheDocument();
    expectRegionsInOrder([
      "宏观简报",
      "今日决策台",
      "跨域判断链",
      "市场事件流",
      "跨域市场板",
      "传导链",
      "数据诊断",
    ]);
    const overview = screen.getByRole("region", { name: "宏观简报" });
    expect(within(overview).getByText("总览：风险偏好等待利率与流动性确认")).toBeInTheDocument();
    expect(within(overview).getAllByText("风险偏好部分确认").length).toBeGreaterThan(0);
    expect(within(overview).getByText("中低置信度")).toBeInTheDocument();
    expect(within(overview).getByText("加密 beta 需要美元流动性配合。")).toBeInTheDocument();
    const decisionConsole = screen.getByRole("region", { name: "今日决策台" });
    expectRegionsInOrderWithin(decisionConsole, [
      "3 个最重要变化",
      "确认 / 背离",
      "流动性压力",
      "未来 24/72h 催化剂",
      "交易映射",
      "未来 2 周情景",
      "Watchlist 与触发提醒",
      "数据可信度层",
    ]);
    const topChanges = within(decisionConsole).getByRole("region", {
      name: "3 个最重要变化",
    });
    expect(within(decisionConsole).getByText("SOFR 高于 IORB")).toBeInTheDocument();
    expect(
      within(topChanges).getByText(
        "SOFR-IORB +7bp · 最新 7bp · NY Fed / Federal Reserve · 2026-05-20 · 高",
      ),
    ).toBeInTheDocument();
    expect(within(topChanges).queryByText("资金面 · 高")).not.toBeInTheDocument();
    expect(
      within(topChanges).getByText(
        "SOFR-IORB +7bp · 最新 7bp · source=NY Fed / Federal Reserve · as-of=2026-05-20",
      ),
    ).toBeInTheDocument();
    expect(within(decisionConsole).getByText("高收益债利差压力")).toBeInTheDocument();
    expect(within(decisionConsole).getByText("美股代理可用")).toBeInTheDocument();
    expect(within(decisionConsole).getByText("IWM 样本不足")).toBeInTheDocument();
    const liquidityPressure = within(decisionConsole).getByRole("region", { name: "流动性压力" });
    expect(within(liquidityPressure).getByText("7.0/10 · 走廊抽水")).toBeInTheDocument();
    expect(
      within(liquidityPressure).getByText(
        "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
      ),
    ).toBeInTheDocument();
    expect(
      within(liquidityPressure).getByText(
        "SOFR-IORB 走廊压力 · 7bp · 1w +6bp · 1m +11bp · 走廊压力",
      ),
    ).toBeInTheDocument();
    expect(
      within(liquidityPressure).getByText("净流动性 · $5.78T · 1w -$60B · 1m -$120B · 净抽水"),
    ).toBeInTheDocument();
    expect(
      within(liquidityPressure).getByText(
        "失效：若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
      ),
    ).toBeInTheDocument();
    const futureCatalysts = within(decisionConsole).getByRole("region", {
      name: "未来 24/72h 催化剂",
    });
    expect(within(futureCatalysts).getByText("实际利率突破")).toBeInTheDocument();
    expect(within(futureCatalysts).getByText("24h · 高 · 情景触发")).toBeInTheDocument();
    expect(within(futureCatalysts).getByText("FOMC 决议")).toBeInTheDocument();
    expect(within(futureCatalysts).getByText("24h · 高 · 官方日历")).toBeInTheDocument();
    expect(within(futureCatalysts).getByText("高收益债利差进入困境区")).toBeInTheDocument();
    expect(within(futureCatalysts).getByText("72h · 中 · 情景触发")).toBeInTheDocument();
    expect(within(futureCatalysts).getByRole("link", { name: "来源" })).toHaveAttribute(
      "href",
      "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    );
    const dataCredibility = within(decisionConsole).getByRole("region", {
      name: "数据可信度层",
    });
    expect(within(dataCredibility).getByText("2 issue(s)")).toBeInTheDocument();
    expect(within(dataCredibility).getByText("SPX")).toBeInTheDocument();
    expect(
      within(dataCredibility).getByText("5312.40 点 · FRED · 2026-05-20 · 可用"),
    ).toBeInTheDocument();
    expect(within(dataCredibility).getByText("HY OAS")).toBeInTheDocument();
    expect(
      within(dataCredibility).getByText("2.80 % · FRED · 2026-05-17 · 过期"),
    ).toBeInTheDocument();
    expect(within(dataCredibility).getByText("缺少当前数据：SPY")).toBeInTheDocument();
    const tradeMap = within(decisionConsole).getByRole("region", { name: "交易映射" });
    expect(within(tradeMap).getByText("风险降档 / 信用敏感")).toBeInTheDocument();
    expect(within(tradeMap).getByText("BIL · 现金/短债 · 做多/防守")).toBeInTheDocument();
    expect(within(tradeMap).getByText("QQQ · 纳斯达克 · 回避/做空代理")).toBeInTheDocument();
    expect(within(tradeMap).getByText("HYG · 高收益信用 · 低配")).toBeInTheDocument();
    expect(within(tradeMap).getByRole("heading", { name: "行动清单" })).toBeInTheDocument();
    expect(
      within(decisionConsole).getByText(
        "确认 · HY OAS 5日走阔 · 观察 HY OAS 5日走阔 是否继续确认。",
      ),
    ).toBeInTheDocument();
    const scenarioCases = within(decisionConsole).getByRole("region", {
      name: "未来 2 周情景",
    });
    expect(within(scenarioCases).getByText("基准情景")).toBeInTheDocument();
    expect(within(scenarioCases).getByText("50% · 未来 2 周")).toBeInTheDocument();
    expect(
      within(scenarioCases).getByText(
        "资金压力维持，信用 beta 继续承压，风险资产反弹先按减仓处理。",
      ),
    ).toBeInTheDocument();
    expect(
      within(scenarioCases).getByText("交易：防守：做多/持有 BIL，低配 QQQ 与 HYG。"),
    ).toBeInTheDocument();
    expect(
      within(scenarioCases).getByText("止损：SOFR 回到 IORB 附近且 HY OAS 明显收窄。"),
    ).toBeInTheDocument();
    expect(within(scenarioCases).getByText("悲观情景")).toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "事件热力" }),
    ).not.toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "事件催化" }),
    ).not.toBeInTheDocument();
    expect(within(decisionConsole).queryByText("10Y 国债拍卖 Bid/Cover")).not.toBeInTheDocument();
    const watchlistAlerts = within(decisionConsole).getByRole("region", {
      name: "Watchlist 与触发提醒",
    });
    expect(within(watchlistAlerts).getByText("BIL · 现金/短债 · 做多/防守")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("QQQ · 纳斯达克 · 回避/做空代理")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("HYG · 高收益信用 · 低配")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("实际利率突破")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("触发 · 24h · 高")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("10年期收益率回落")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("失效")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("缺少当前数据：SPY")).toBeInTheDocument();
    expect(within(watchlistAlerts).getByText("质量 · 阻断")).toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "观察触发 / 失效条件" }),
    ).not.toBeInTheDocument();
    expect(decisionConsole).toHaveTextContent(
      "确认 · SOFR 高于 IORB · 观察 SOFR 高于 IORB 是否继续确认。",
    );
    expect(decisionConsole).toHaveTextContent(
      "确认 · HY OAS 5日走阔 · 观察 HY OAS 5日走阔 是否继续确认。",
    );
    expect(decisionConsole).not.toHaveTextContent("确认：SOFR 高于 IORB / HY OAS 5日走阔");
    expect(decisionConsole).not.toHaveTextContent("60日历史补齐");
    expect(decisionConsole).not.toHaveTextContent("观察 · 24h · 高");
    expect(decisionConsole).not.toHaveTextContent("SPX 跌破趋势");
    expect(decisionConsole).not.toHaveTextContent("risk_down_credit_sensitive");
    expect(decisionConsole).not.toHaveTextContent("missing_asset_spy");
    expect(decisionConsole).not.toHaveTextContent("待确认信号");
    const structuredAnalysis = screen.getByRole("region", { name: "跨域判断链" });
    expect(within(structuredAnalysis).getByText("市场主线")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("市场主线：长端利率维持压力。"),
    ).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("Trade Map · 久期承压 / 质量优于成长"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("美联储沟通")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText(
        "Fed 沟通：2026-05-08 · Waller, Update On Federal Reserve Bank Operations",
      ),
    ).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("Fed 沟通 · 跟踪措辞、投票分歧和政策路径信号。"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("大类资产")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("滞胀冲击")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText(
        "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
      ),
    ).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("SPX · 1w -2.8% · 1m -3.7% · 风险降温"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("利率曲线")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("2s10s · 50bp · 走陡")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("美联储")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("联邦基金有效利率 · 5.33% · 政策约束"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("流动性")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("SOFR-IORB 走廊压力 · 7bp · 走廊压力"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("经济增长")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("实际 GDP · 1.9% y/y · 增长降温"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("就业")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("失业率 · 4.3% · 就业降温")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("通胀")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText("核心 CPI · 5.7% y/y · 再加速"),
    ).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("波动率")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("VIX · 16.9 · Carry")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("信用市场")).toBeInTheDocument();
    expect(within(structuredAnalysis).getByText("HY OAS · 440bp · 走阔")).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText(
        "交易含义：信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。",
      ),
    ).toBeInTheDocument();
    expect(
      within(structuredAnalysis).getByText(
        "失效条件：若 10Y 回落且 2s10s 重新走平，曲线压力降级。",
      ),
    ).toBeInTheDocument();
    const marketEventFlow = screen.getByRole("region", { name: "市场事件流" });
    expect(
      within(marketEventFlow).getByText("中东震荡下，日本追加预算预期升温"),
    ).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("bloomberg.com · 美联储 · 不改主线 · 近期"),
    ).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("油价与美元走强，风险资产低开。")).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("SPX · 美元 · 美联储")).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("FOMC 决议")).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("官方日历 · 政策 · 政策路径 · 0-3天"),
    ).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("2Y 国债拍卖日历")).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("US Treasury · 国债供给 · 拍卖/交割 · 4-7天"),
    ).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("10Y 国债拍卖 Bid/Cover")).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("US Treasury · 国债供给 · 拍卖结果 · 近期"),
    ).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("拍卖结果作为国债需求和期限溢价压力证据。"),
    ).toBeInTheDocument();
    expect(within(marketEventFlow).getByText("Fed 官员讲话")).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("Federal Reserve · 政策 · Fed 沟通 · 近期"),
    ).toBeInTheDocument();
    expect(
      within(marketEventFlow).getByText("跟踪措辞、投票分歧和政策路径信号。"),
    ).toBeInTheDocument();
    expect(within(marketEventFlow).getAllByRole("link", { name: "来源" })).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          href: "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
        }),
      ]),
    );
    const transmission = screen.getByRole("region", { name: "传导链" });
    expect(within(transmission).getByText("宏观总览")).toBeInTheDocument();
    const drivers = screen.getByRole("region", { name: "跨域市场板" });
    expect(within(drivers).getByRole("table", { name: "美股代理快照" })).toBeInTheDocument();
    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getByText("全局历史样本不足")).toBeInTheDocument();
    expect(dataHealth).not.toHaveTextContent("待回填");
    expect(
      within(dataHealth).getByText("需要补充全局宏观历史后再生成总览投影。"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "关键指标" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "当前解读" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "证据板" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "相关页面" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/series", {
        params: { concept_keys: "asset:spx", window: "60d" },
        token: "test-token",
      }),
    );
  });

  it("omits missing decision-console metadata instead of rendering placeholder copy", () => {
    const base = macroOverviewModuleFixture();

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroOverviewModuleFixture({
          module_read: {
            ...base.module_read,
            decision_console: {
              ...(base.module_read.decision_console as Record<string, unknown>),
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
              trade_map: [
                {
                  expression: "risk_down_credit_sensitive",
                  label: "风险降档 / 信用敏感",
                  legs: [{ asset: "BIL", label: "现金/短债", action: "做多/防守" }],
                  confirms: ["SOFR 高于 IORB"],
                  invalidates: ["HY OAS 收窄"],
                },
              ],
            },
          },
        })}
        moduleId="overview"
        pageKind="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    const decisionConsole = screen.getByRole("region", { name: "今日决策台" });
    expect(within(decisionConsole).getByText("基准情景")).toBeInTheDocument();
    expect(within(decisionConsole).getAllByText("风险降档 / 信用敏感").length).toBeGreaterThan(0);
    expect(decisionConsole).not.toHaveTextContent("概率待确认");
    expect(decisionConsole).not.toHaveTextContent("窗口待确认");
    expect(decisionConsole).not.toHaveTextContent("确认：待确认");
    expect(decisionConsole).not.toHaveTextContent("失效：待确认");
  });

  it("renders backend macro fields instead of empty placeholders", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroOverviewModuleFixture({
          module_read: {
            headline: "",
            regime_label: "期限溢价压力",
            confidence_label: "中等置信度",
            trade_map: {},
          },
        })}
        moduleId="overview"
        pageKind="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    const overview = screen.getByRole("region", { name: "宏观简报" });
    expect(within(overview).getAllByText("期限溢价压力").length).toBeGreaterThan(0);
    expect(within(overview).queryByText("{}")).not.toBeInTheDocument();
    expect(within(overview).queryByText("暂无")).not.toBeInTheDocument();
    expect(overview).not.toHaveTextContent("term_premium_pressure");
  });

  it("does not use snapshot status as module brief copy when read fields are missing", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroOverviewModuleFixture({
          module_read: {},
          snapshot: {
            ...macroOverviewModuleFixture().snapshot,
            status: "partial",
            status_label: "部分可用",
          },
        })}
        moduleId="overview"
        pageKind="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    expect(screen.queryByRole("region", { name: "宏观简报" })).not.toBeInTheDocument();
    expect(screen.queryByText("缺少模块解读")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();

    const decisionConsole = screen.getByRole("region", { name: "今日决策台" });
    expect(
      within(decisionConsole).getByRole("region", { name: "确认 / 背离" }),
    ).toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "3 个最重要变化" }),
    ).not.toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "交易映射" }),
    ).not.toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "未来 2 周情景" }),
    ).not.toBeInTheDocument();
    expect(
      within(decisionConsole).queryByRole("region", { name: "数据可信度层" }),
    ).not.toBeInTheDocument();
    expect(decisionConsole).not.toHaveTextContent("暂无关键变化");
    expect(decisionConsole).not.toHaveTextContent("暂无交易映射");
    expect(decisionConsole).not.toHaveTextContent("暂无情景计划");
    expect(decisionConsole).not.toHaveTextContent("暂无阻断缺口");
  });

  it("does not render a data credibility fallback section for orphan quality blockers", () => {
    const baseModule = macroOverviewModuleFixture();
    const decisionConsole: Record<string, unknown> = {
      ...(baseModule.module_read.decision_console as Record<string, unknown>),
      quality_blockers: [
        {
          code: "missing_stfm",
          label: "缺少 OFR STFM",
          description: "需要真实 funding market 数据确认。",
          severity: "error",
        },
      ],
    };
    delete decisionConsole.data_credibility;

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroOverviewModuleFixture({
          module_read: {
            ...baseModule.module_read,
            decision_console: decisionConsole,
          },
        })}
        moduleId="overview"
        pageKind="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    const decisionConsoleRegion = screen.getByRole("region", { name: "今日决策台" });
    expect(
      within(decisionConsoleRegion).queryByRole("region", { name: "数据可信度层" }),
    ).not.toBeInTheDocument();
    expect(decisionConsoleRegion).not.toHaveTextContent("缺少 OFR STFM");
  });

  it("removes the leaf module brief panel when read fields are missing", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          module_read: {},
          snapshot: {
            ...macroModuleFixture().snapshot,
            status: "partial",
            status_label: "部分可用",
          },
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(screen.queryByRole("region", { name: "模块简报" })).not.toBeInTheDocument();
    expect(screen.queryByText("缺少模块解读")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "主市场证据" })).toBeInTheDocument();
  });

  it("removes the leaf market evidence panel when chart and tables are both empty", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          primary_chart: { id: "equity_proxy_performance", min_points: 2, series: [] },
          tables: [],
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(screen.queryByRole("region", { name: "主市场证据" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无可绘制序列")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "美股风险诊断" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
  });

  it("removes the leaf driver board when evidence and transmission are both absent", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          module_evidence: {
            confirmations: [],
            contradictions: [],
            watch_triggers: [],
            invalidations: [],
          },
          transmission: [],
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByRole("region", { name: "主市场证据" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "驱动与反证" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无可用证据")).not.toBeInTheDocument();
  });

  it("removes empty data-gap details when a leaf module has no gaps", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          data_health: {
            summary_label: "模块数据可用",
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getAllByText("模块数据可用").length).toBeGreaterThan(0);
    expect(within(dataHealth).getByText("0")).toBeInTheDocument();
    expect(within(dataHealth).queryByText("缺口明细")).not.toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无数据缺口")).not.toBeInTheDocument();
  });

  it("removes the leaf source table when provenance rows are absent", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          data_health: {
            summary_label: "模块数据可用",
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
          provenance: { rows: [] },
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getByText("0 个来源")).toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无来源")).not.toBeInTheDocument();
    expect(within(dataHealth).queryByText("来源状态")).not.toBeInTheDocument();
    expect(within(dataHealth).queryByRole("table", { name: "数据源" })).not.toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无数据源元信息")).not.toBeInTheDocument();
  });

  it("does not display raw leaf diagnostics summary status codes", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          data_health: {
            summary_label: null,
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
          provenance: { rows: [] },
        })}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(dataHealth).not.toHaveTextContent("ok");
    expect(dataHealth).not.toHaveTextContent("正常");
  });

  it("renders asset-class normalized return page from backend payloads", async () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture()}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByRole("region", { name: "美股风险模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "美股风险诊断", "驱动与反证", "数据诊断"]);
    expect(screen.getByRole("region", { name: "主市场证据" })).toBeInTheDocument();
    const diagnostics = screen.getByRole("region", { name: "美股风险诊断" });
    expect(within(diagnostics).getByText("美股风险诊断 · 美股降温")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "美股风险偏好走弱：大盘和成长承压，小盘/高 beta 未确认，风险资产需要降档。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("SPX")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -3.8% · 1m 0%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("CFTC S&P 净投机")).toBeInTheDocument();
    expect(within(diagnostics).getByText("-120k · 1w -60k · 1m -100k")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "美股降温：降低股票、加密 beta 和高收益信用暴露，等待小盘和成长股修复。",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块简报" })).toBeInTheDocument();
    const drivers = screen.getByRole("region", { name: "驱动与反证" });
    expect(drivers).toBeInTheDocument();
    expect(within(drivers).getByText("美股风险")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "关键指标" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块判断" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块证据" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "数据来源" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块数据健康" })).not.toBeInTheDocument();
    expect(screen.queryByText("缺少 SRF")).not.toBeInTheDocument();
    expect(screen.getByText("Yahoo")).toBeInTheDocument();
    expect(screen.getByText("美股风险偏好")).toBeInTheDocument();
    expect(await screen.findByText("10%")).toBeInTheDocument();
  });

  it("renders bonds asset-class diagnostics with the backend label", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          snapshot: {
            ...macroModuleFixture().snapshot,
            module_id: "assets/bonds",
            route_path: "/macro/assets/bonds",
            title: "债券资产",
            subtitle: "久期、通胀保护、综合债与信用确认",
            question: "债券市场是在释放久期压力，还是确认避险需求？",
          },
          module_read: {
            headline: "债券资产：信用久期双压",
            regime_label: "信用久期双压",
            confidence_label: "模块覆盖 8/10",
            asset_class_diagnostics: {
              label: "债券风险诊断",
              regime: "bond_credit_pressure",
              regime_label: "信用久期双压",
              summary: "债券横截面偏防守：长久期回撤且 HYG 跑输 LQD，信用利差同步走阔。",
              rows: [
                {
                  key: "tlt",
                  label: "TLT",
                  change_1w_pct: -5.88,
                  change_1m_pct: -4,
                  status: "duration_pressure",
                  status_label: "久期承压",
                },
                {
                  key: "hy_oas",
                  label: "HY OAS",
                  current_bp: 340,
                  change_1w_bp: 30,
                  change_1m_bp: 40,
                  status: "credit_widening",
                  status_label: "信用走阔",
                },
              ],
              implications: [
                "信用久期双压：降低 HYG/JNK 和长久期暴露，优先现金、短债或高质量信用。",
              ],
              invalidations: ["若 TLT/IEF 1w 转正且 HYG 不再跑输 LQD，信用久期双压读法降级。"],
            },
          },
        })}
        moduleId="assets/bonds"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/bonds" },
    );

    expect(screen.getByRole("region", { name: "债券资产模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "债券风险诊断", "驱动与反证", "数据诊断"]);
    const diagnostics = screen.getByRole("region", { name: "债券风险诊断" });
    expect(within(diagnostics).getByText("债券风险诊断 · 信用久期双压")).toBeInTheDocument();
    expect(within(diagnostics).getByText("TLT")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -5.9% · 1m -4%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("HY OAS")).toBeInTheDocument();
    expect(within(diagnostics).getByText("340bp · 1w +30bp · 1m +40bp")).toBeInTheDocument();
  });

  it("renders commodities asset-class diagnostics with the backend label", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          snapshot: {
            ...macroModuleFixture().snapshot,
            module_id: "assets/commodities",
            route_path: "/macro/assets/commodities",
            title: "商品冲击",
            subtitle: "能源、贵金属、铜与通胀脉冲",
            question: "商品价格是在制造通胀压力，还是只是局部供需扰动？",
          },
          module_read: {
            headline: "商品冲击：能源通胀冲击",
            regime_label: "能源通胀冲击",
            confidence_label: "模块覆盖 13/13",
            asset_class_diagnostics: {
              label: "商品冲击诊断",
              regime: "energy_inflation_shock",
              regime_label: "能源通胀冲击",
              summary:
                "商品主线偏能源通胀冲击：原油和天然气同步上行，铜确认需求，贵金属未给防守确认。",
              rows: [
                {
                  key: "wti",
                  label: "WTI",
                  change_1w_pct: 15.79,
                  change_1m_pct: 10,
                  status: "energy_up",
                  status_label: "能源上行",
                },
                {
                  key: "copper",
                  label: "Copper",
                  change_1w_pct: 5.88,
                  change_1m_pct: 8,
                  status: "industrial_bid",
                  status_label: "工业金属走强",
                },
              ],
              implications: ["能源通胀冲击：保留能源/美元受益表达，降低长久期和高估值风险资产。"],
              invalidations: ["若 WTI/Brent 1w 转负且 NatGas 回落，能源通胀冲击读法降级。"],
            },
          },
        })}
        moduleId="assets/commodities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/commodities" },
    );

    expect(screen.getByRole("region", { name: "商品冲击模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "商品冲击诊断", "驱动与反证", "数据诊断"]);
    const diagnostics = screen.getByRole("region", { name: "商品冲击诊断" });
    expect(within(diagnostics).getByText("商品冲击诊断 · 能源通胀冲击")).toBeInTheDocument();
    expect(within(diagnostics).getByText("WTI")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w +15.8% · 1m +10%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("Copper")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w +5.9% · 1m +8%")).toBeInTheDocument();
  });

  it("renders fx asset-class diagnostics with the backend label", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          snapshot: {
            ...macroModuleFixture().snapshot,
            module_id: "assets/fx",
            route_path: "/macro/assets/fx",
            title: "美元压力",
            subtitle: "DXY、广义美元、主要汇率与货币 ETF",
            question: "美元是在收紧离岸流动性，还是给风险资产让路？",
          },
          module_read: {
            headline: "美元压力：美元挤压",
            regime_label: "美元挤压",
            confidence_label: "模块覆盖 14/14",
            asset_class_diagnostics: {
              label: "美元压力诊断",
              regime: "dollar_squeeze",
              regime_label: "美元挤压",
              summary: "美元压力偏紧：DXY 和广义美元走强，欧元、日元与人民币同步确认离岸美元需求。",
              rows: [
                {
                  key: "dxy",
                  label: "DXY",
                  change_1w_pct: 1.98,
                  change_1m_pct: 3,
                  status: "dollar_up",
                  status_label: "美元走强",
                },
                {
                  key: "eurusd",
                  label: "EURUSD",
                  change_1w_pct: -3.03,
                  change_1m_pct: -4,
                  status: "usd_up",
                  status_label: "美元走强",
                },
              ],
              implications: [
                "美元挤压：降低新兴市场、商品进口国和高 beta 风险资产，保留美元现金或 UUP 防守。",
              ],
              invalidations: ["若 DXY/Broad USD 1w 转负且 EURUSD 修复，美元挤压读法降级。"],
            },
          },
        })}
        moduleId="assets/fx"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/fx" },
    );

    expect(screen.getByRole("region", { name: "美元压力模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "美元压力诊断", "驱动与反证", "数据诊断"]);
    const diagnostics = screen.getByRole("region", { name: "美元压力诊断" });
    expect(within(diagnostics).getByText("美元压力诊断 · 美元挤压")).toBeInTheDocument();
    expect(within(diagnostics).getByText("DXY")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w +2% · 1m +3%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("EURUSD")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -3% · 1m -4%")).toBeInTheDocument();
  });

  it("renders crypto asset-class diagnostics with the backend label", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture({
          snapshot: {
            ...macroModuleFixture().snapshot,
            module_id: "assets/crypto",
            route_path: "/macro/assets/crypto",
            title: "加密资产",
            subtitle: "BTC / ETH 宏观 beta",
            question: "BTC/ETH 是在确认宏观 risk-on，还是只是自身波动？",
          },
          module_read: {
            headline: "加密资产：加密 beta 降温",
            regime_label: "加密 beta 降温",
            confidence_label: "模块覆盖 2/2",
            asset_class_diagnostics: {
              label: "加密 beta 诊断",
              regime: "crypto_beta_unwind",
              regime_label: "加密 beta 降温",
              summary:
                "加密资产同步降温：BTC 和 ETH 单周回撤，ETH 跑输 BTC，宏观 risk-on 需要降档。",
              rows: [
                {
                  key: "btc",
                  label: "BTC",
                  change_1w_pct: -4.26,
                  change_1m_pct: -10,
                  status: "crypto_beta_down",
                  status_label: "加密降温",
                },
                {
                  key: "eth",
                  label: "ETH",
                  change_1w_pct: -6.82,
                  change_1m_pct: -18,
                  status: "crypto_beta_down",
                  status_label: "加密降温",
                },
              ],
              implications: [
                "加密 beta 降温：降低 BTC/ETH 和高 beta 风险资产暴露，等待 BTC 稳定与 ETH 不再跑输。",
              ],
              invalidations: ["若 BTC/ETH 1w 转正且 ETH 不再跑输 BTC，加密降温读法降级。"],
            },
          },
        })}
        moduleId="assets/crypto"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/crypto" },
    );

    expect(screen.getByRole("region", { name: "加密资产模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "加密 beta 诊断", "驱动与反证", "数据诊断"]);
    const diagnostics = screen.getByRole("region", { name: "加密 beta 诊断" });
    expect(within(diagnostics).getByText("加密 beta 诊断 · 加密 beta 降温")).toBeInTheDocument();
    expect(within(diagnostics).getByText("BTC")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -4.3% · 1m -10%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("ETH")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -6.8% · 1m -18%")).toBeInTheDocument();
  });

  it("renders credit stress diagnostics between market evidence and drivers", async () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroCreditStressModuleFixture()}
        moduleId="credit/stress"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/credit/stress" },
    );

    expect(screen.getByRole("region", { name: "信用压力分解模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "信用压力诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "信用压力诊断" });
    expect(within(diagnostics).getByText("信用压力诊断 · 尾部走阔")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("HY OAS")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("420bp · 1w +30bp · 1m +50bp · 3m +70bp"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("CCC-HY 尾部")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("530bp · 1w +90bp · 1m +100bp · 3m +160bp"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("HYG/LQD 信用 ETF")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("HYG 1w -1.3% · LQD 1w +0.9% · 相对 -2.2%"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("NFCI 金融条件")).toBeInTheDocument();
    expect(within(diagnostics).getByText("-0.1 · 1w +0.2 · 1m +0.3 · 3m +0.5")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。"),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("credit:");
  });

  it("renders liquidity diagnostics between market evidence and drivers", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroLiquidityRrpTgaModuleFixture()}
        moduleId="liquidity/rrp-tga"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/liquidity/rrp-tga" },
    );

    expect(screen.getByRole("region", { name: "RRP / TGA模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "流动性诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "流动性诊断" });
    expect(within(diagnostics).getByText("流动性诊断 · 走廊抽水")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("SOFR-IORB 走廊压力")).toBeInTheDocument();
    expect(within(diagnostics).getByText("7bp · 1w +6bp · 1m +11bp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("RRP 缓冲")).toBeInTheDocument();
    expect(within(diagnostics).getByText("$760B · 1w -$60B · 1m -$140B")).toBeInTheDocument();
    expect(within(diagnostics).getByText("净流动性")).toBeInTheDocument();
    expect(within(diagnostics).getByText("$5.78T · 1w -$60B · 1m -$120B")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
      ),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("liquidity:");
  });

  it("renders inflation diagnostics between market evidence and drivers", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroInflationModuleFixture()}
        moduleId="economy/inflation"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/economy/inflation" },
    );

    expect(screen.getByRole("region", { name: "通胀仪表盘模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "通胀诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "通胀诊断" });
    expect(within(diagnostics).getByText("通胀诊断 · 通胀再加速")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("CPI 同比")).toBeInTheDocument();
    expect(within(diagnostics).getByText("5.3% y/y · 1m +1.3pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("核心 CPI 同比")).toBeInTheDocument();
    expect(within(diagnostics).getByText("5.7% y/y · 1m +1.3pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("10Y 通胀补偿")).toBeInTheDocument();
    expect(within(diagnostics).getByText("2.6% · 1w +10bp · 1m +25bp")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。",
      ),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("inflation:");

    const drivers = screen.getByRole("region", { name: "驱动与反证" });
    expect(within(drivers).getByText("PCE 发布窗口")).toBeInTheDocument();
    expect(drivers).not.toHaveTextContent("尚待确认");
    expect(drivers).not.toHaveTextContent("待确认");
  });

  it("renders employment diagnostics between market evidence and drivers", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroEmploymentModuleFixture()}
        moduleId="economy/employment"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/economy/employment" },
    );

    expect(screen.getByRole("region", { name: "就业市场模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "就业诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "就业诊断" });
    expect(within(diagnostics).getByText("就业诊断 · 就业降温")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "就业降温：失业率与初请上行、非农动能放缓，增长风险开始压过软着陆叙事。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("失业率")).toBeInTheDocument();
    expect(within(diagnostics).getByText("4.3% · 1m +0.3pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("非农新增")).toBeInTheDocument();
    expect(within(diagnostics).getByText("80k · 1m -140k")).toBeInTheDocument();
    expect(within(diagnostics).getByText("初请失业金")).toBeInTheDocument();
    expect(within(diagnostics).getByText("260k · 1w +4k · 1m +30k")).toBeInTheDocument();
    expect(within(diagnostics).getByText("职位空缺")).toBeInTheDocument();
    expect(within(diagnostics).getByText("7.4M · 1m -0.6M")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀同步配合。",
      ),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。",
      ),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("labor:");
  });

  it("renders growth diagnostics between market evidence and drivers", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroGdpModuleFixture()}
        moduleId="economy/gdp"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/economy/gdp" },
    );

    expect(screen.getByRole("region", { name: "GDP 增长模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "增长诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "增长诊断" });
    expect(within(diagnostics).getByText("增长诊断 · 增长降温")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "增长降温：实际 GDP、工业生产和消费动能同步放缓，风险资产盈利预期需要降级。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("实际 GDP 同比")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1.9% y/y · 1q -0.8pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("GDPNow")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1.5% SAAR · 1m -1.7pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("工业生产同比")).toBeInTheDocument();
    expect(within(diagnostics).getByText("-1.5% y/y · 1m -2pp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("住房开工")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1.3M · 1m -150k")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "增长降温：降低盈利周期和高 beta 暴露，等待就业或消费重新确认。",
      ),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。",
      ),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("economy:");
    expect(diagnostics).not.toHaveTextContent("consumer:");
  });

  it("renders volatility diagnostics between market evidence and drivers", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroVolatilityVixModuleFixture()}
        moduleId="volatility/vix"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/volatility/vix" },
    );

    expect(screen.getByRole("region", { name: "VIX 结构模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "波动率诊断", "驱动与反证", "数据诊断"]);

    const diagnostics = screen.getByRole("region", { name: "波动率诊断" });
    expect(within(diagnostics).getByText("波动率诊断 · 期限 Contango")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("VIX 现货")).toBeInTheDocument();
    expect(within(diagnostics).getByText("16.9 · 1w -2.1 · 1m -4.1")).toBeInTheDocument();
    expect(within(diagnostics).getByText("VIX1D-VIX 当日溢价")).toBeInTheDocument();
    expect(within(diagnostics).getByText("0.4pts · 1w +1.4pts · 1m +1.4pts")).toBeInTheDocument();
    expect(within(diagnostics).getByText("VIX9D-VIX 近端溢价")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1.1pts · 1w +1.6pts · 1m +2.1pts")).toBeInTheDocument();
    expect(within(diagnostics).getByText("VIX3M-VIX 期限溢价")).toBeInTheDocument();
    expect(within(diagnostics).getByText("6.9pts · 1w +1.7pts · 1m +2.9pts")).toBeInTheDocument();
    expect(within(diagnostics).getByText("VVIX 波动率凸性")).toBeInTheDocument();
    expect(within(diagnostics).getByText("88 · 1w +2 · 1m +4")).toBeInTheDocument();
    expect(within(diagnostics).getByText("SKEW 尾部风险")).toBeInTheDocument();
    expect(within(diagnostics).getByText("144 · 1w +2.8 · 1m +5.8")).toBeInTheDocument();
    expect(within(diagnostics).getByText("VIXY/VIXM 前端压力")).toBeInTheDocument();
    expect(within(diagnostics).getByText("0.62x · 1w -6.7% · 1m -6.7%")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。",
      ),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。"),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent("vol:");
  });

  it("renders the asset landing page as a market board before supporting readouts", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          snapshot: {
            ...macroAssetsModuleFixture().snapshot,
            title: "资产总览后端标题",
          },
          tables: [assetDashboardTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    expect(screen.getByRole("region", { name: "资产总览后端标题模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["核心资产行情", "跨资产诊断", "今日判断", "数据诊断", "60日相关性"]);
    expect(screen.queryByRole("region", { name: "关键指标" })).not.toBeInTheDocument();

    const diagnostics = screen.getByRole("region", { name: "跨资产诊断" });
    expect(within(diagnostics).getByText("跨资产诊断 · 滞胀冲击")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("SPX")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w -3.1% · 1m -5%")).toBeInTheDocument();
    expect(within(diagnostics).getByText("DXY")).toBeInTheDocument();
    expect(within(diagnostics).getByText("1w +1% · 1m +3%")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。"),
    ).toBeInTheDocument();

    const judgment = screen.getByRole("region", { name: "今日判断" });
    expect(within(judgment).getByText("风险资产偏震荡")).toBeInTheDocument();
    expect(within(judgment).getByText("最新覆盖")).toBeInTheDocument();
    expect(within(judgment).getByText("历史覆盖")).toBeInTheDocument();

    const dashboard = screen.getByRole("region", { name: "核心资产行情" });
    expect(within(dashboard).getByRole("table", { name: "美股" })).toBeInTheDocument();
    expect(within(dashboard).getByRole("table", { name: "债券" })).toBeInTheDocument();
    expect(within(dashboard).getByRole("table", { name: "商品" })).toBeInTheDocument();
    expect(within(dashboard).getByRole("table", { name: "外汇" })).toBeInTheDocument();
    expect(within(dashboard).getByRole("table", { name: "加密货币" })).toBeInTheDocument();
    expect(
      within(dashboard)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(expect.arrayContaining(["代码", "名称", "最新", "日涨跌幅", "日期"]));
    expect(
      within(dashboard).queryByRole("columnheader", { name: "20日变化" }),
    ).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("fixture")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("暂无")).not.toBeInTheDocument();
    expect(within(dashboard).getByRole("link", { name: "美股详情" })).toHaveAttribute(
      "href",
      "/macro/assets/equities",
    );

    expect(screen.getByText("风险资产偏震荡")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "数据来源" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "模块数据健康" })).not.toBeInTheDocument();
  });

  it("removes empty pair groups from the asset correlation surface", async () => {
    apiMock.getApiImpl = async (path) => {
      if (path === "/api/macro/assets/correlation") return ok(macroCorrelationFixture());
      throw new Error(`unexpected path ${path}`);
    };

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [assetDashboardTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const correlation = await screen.findByRole("region", { name: "60日相关性" });
    await waitFor(() => expect(within(correlation).getByText("SPY / QQQ")).toBeInTheDocument());
    expect(within(correlation).getByText("正相关")).toBeInTheDocument();
    expect(within(correlation).queryByText("负相关")).not.toBeInTheDocument();
    expect(within(correlation).queryByText("暂无")).not.toBeInTheDocument();
  });

  it("removes the asset correlation surface when no available pairs exist", async () => {
    apiMock.getApiImpl = async (path) => {
      if (path === "/api/macro/assets/correlation") {
        return ok({
          ...macroCorrelationFixture(),
          assets: [],
          matrix: [],
          pairs: [],
          data_gaps: [],
        });
      }
      throw new Error(`unexpected path ${path}`);
    };

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [assetDashboardTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    await waitFor(() =>
      expect(apiMock.getApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "test-token",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "60日相关性" })).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("暂无相关性样本")).not.toBeInTheDocument();
    expect(screen.queryByText("暂无可用资产")).not.toBeInTheDocument();
  });

  it("keeps asset correlation errors visible without no-data copy", async () => {
    apiMock.getApiImpl = async (path) => {
      if (path === "/api/macro/assets/correlation") {
        throw new Error("correlation unavailable");
      }
      throw new Error(`unexpected path ${path}`);
    };

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [assetDashboardTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const correlation = await screen.findByRole("region", { name: "60日相关性" });
    await waitFor(() =>
      expect(
        within(correlation).getByText("相关性暂不可用：correlation unavailable"),
      ).toBeInTheDocument(),
    );
    expect(within(correlation).getByText("暂不可用")).toBeInTheDocument();
    expect(within(correlation).queryByText("暂无")).not.toBeInTheDocument();
  });

  it("does not render pending placeholders when asset snapshot metadata is absent", () => {
    const module = macroAssetsModuleFixture({
      snapshot: {
        ...macroAssetsModuleFixture().snapshot,
        asof_date: null,
        asof_label: null,
      },
      tables: [assetDashboardTable({ includeDate: false, includeSource: false })],
      daily_brief: {
        status: "partial",
        headline: "今日判断：样本不足",
        data_quality: {
          status: "insufficient_history",
        },
        blocks: [],
      },
    });

    renderWithProviders(
      <MacroModulePageRenderer
        module={module}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    expect(screen.queryByText("待确认")).not.toBeInTheDocument();
    const dashboard = screen.getByRole("region", { name: "核心资产行情" });
    expect(within(dashboard).queryByText("截至")).not.toBeInTheDocument();
    const judgment = screen.getByRole("region", { name: "今日判断" });
    expect(within(judgment).queryByLabelText("今日判断数据质量")).not.toBeInTheDocument();
    expect(within(judgment).queryByText("最新覆盖")).not.toBeInTheDocument();
    expect(within(judgment).queryByText("历史覆盖")).not.toBeInTheDocument();
  });

  it("does not expose raw asset snapshot or correlation dates without backend labels", async () => {
    apiMock.getApiImpl = async (path) => {
      if (path === "/api/macro/assets/correlation") {
        return ok({
          ...macroCorrelationFixture(),
          asof_date: "2026-06-11",
          window: "60d",
        });
      }
      throw new Error(`unexpected path ${path}`);
    };

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          snapshot: {
            ...macroAssetsModuleFixture().snapshot,
            asof_date: "2026-06-10",
            asof_label: null,
          },
          tables: [assetDashboardTable({ includeDate: false })],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dashboard = screen.getByRole("region", { name: "核心资产行情" });
    expect(within(dashboard).queryByText("截至")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("2026-06-10")).not.toBeInTheDocument();

    const correlation = await screen.findByRole("region", { name: "60日相关性" });
    await waitFor(() => expect(within(correlation).getByText("SPY / QQQ")).toBeInTheDocument());
    expect(correlation).not.toHaveTextContent("截至 2026-06-11");
    expect(correlation).not.toHaveTextContent("60d");
  });

  it("drops asset market rows without current price evidence and omits missing optional cells", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [assetDashboardTable({ includeDate: false, includeMissingLatestRow: true })],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dashboard = screen.getByRole("region", { name: "核心资产行情" });
    expect(within(dashboard).getByText("^GSPC")).toBeInTheDocument();
    expect(within(dashboard).queryByText("IWM")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("暂无")).not.toBeInTheDocument();
    expect(within(dashboard).queryByText("缺少日期")).not.toBeInTheDocument();
    expect(
      within(within(dashboard).getByRole("table", { name: "美股" })).queryByText("2026-05-20"),
    ).not.toBeInTheDocument();
  });

  it("removes the asset market surface when no asset rows exist", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [{ ...assetDashboardTable(), rows: [] }],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    expect(screen.queryByRole("region", { name: "核心资产行情" })).not.toBeInTheDocument();
    expect(screen.queryByText("大类资产快照暂无可展示行。")).not.toBeInTheDocument();
    expect(screen.queryByText(/暂无.*快照/)).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "跨资产诊断" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
  });

  it("removes the asset data-gap empty state when gap count is zero", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          data_health: {
            summary_label: "资产数据可用",
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getByText("0")).toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无数据缺口")).not.toBeInTheDocument();
  });

  it("removes the asset source table when provenance rows are absent", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          data_health: {
            summary_label: "资产数据可用",
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
          provenance: { rows: [] },
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getAllByText("0").length).toBeGreaterThan(0);
    expect(within(dataHealth).queryByRole("table", { name: "数据源" })).not.toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无数据源元信息")).not.toBeInTheDocument();
  });

  it("does not display raw asset diagnostics summary status codes", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          data_health: {
            summary_label: null,
            summary_status: "ok",
            module_gaps: [],
            chart_gaps: [],
            global_gaps: [],
          },
          provenance: { rows: [] },
          tables: [assetDashboardTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(dataHealth).not.toHaveTextContent("ok");
  });

  it("removes the asset availability drawer when coverage rows are absent", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [assetDashboardTable(), assetAvailabilityTable()],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).queryByText("覆盖")).not.toBeInTheDocument();
    expect(within(dataHealth).queryByText("暂无覆盖明细。")).not.toBeInTheDocument();
  });

  it("renders only populated asset availability cells without placeholder copy", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture({
          tables: [
            assetDashboardTable(),
            assetAvailabilityTable([
              {
                row_id: "asset:spx",
                cells: {
                  item: { display_value: "SPX", sort_value: "SPX" },
                  status: { display_value: "可用", sort_value: "ok" },
                },
              },
              {
                row_id: "asset:empty",
                cells: {
                  item: { display_value: "", sort_value: "empty" },
                  status: { display_value: "", sort_value: "" },
                },
              },
            ]),
          ],
        })}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    fireEvent.click(within(dataHealth).getByText("覆盖"));
    const coverageTable = within(dataHealth).getByRole("table", {
      name: "数据可用性 / 代理说明",
    });
    expect(within(coverageTable).getByText("SPX")).toBeInTheDocument();
    expect(within(coverageTable).getByText("可用")).toBeInTheDocument();
    expect(coverageTable).not.toHaveTextContent("暂无");
    expect(coverageTable).not.toHaveTextContent("asset:empty");
  });

  it("removes the asset judgement panel when daily brief is absent", () => {
    const module = macroAssetsModuleFixture({
      daily_brief: null,
      module_read: {
        summary: "模块摘要不能替代正式今日判断。",
      },
      tables: [assetDashboardTable()],
    });

    renderWithProviders(
      <MacroModulePageRenderer
        module={module}
        moduleId="assets"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    expect(screen.queryByRole("region", { name: "今日判断" })).not.toBeInTheDocument();
    expect(screen.queryByText("模块摘要不能替代正式今日判断。")).not.toBeInTheDocument();
    expect(screen.queryByText("缺少今日判断")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据诊断" })).toBeInTheDocument();
  });

  it("keeps a stable chart loading state while backend series is pending", async () => {
    let resolveSeries: (value: unknown) => void = () => {
      throw new Error("series resolver was not initialized");
    };
    apiMock.getApiImpl = async (path, options) => {
      if (path === "/api/macro/series") {
        return new Promise<unknown>((resolve) => {
          resolveSeries = resolve;
        });
      }
      throw new Error(`unexpected path ${path} ${JSON.stringify(options)}`);
    };

    renderWithProviders(
      <MacroModulePageRenderer
        module={macroModuleFixture()}
        moduleId="assets/equities"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(await screen.findByRole("status", { name: "美股代理表现加载状态" })).toHaveTextContent(
      "图表序列加载中",
    );
    expect(screen.queryByText("chart_series_missing")).not.toBeInTheDocument();

    resolveSeries(ok(macroSeriesFixture(["asset:spx"])));

    expect(await screen.findByText("10%")).toBeInTheDocument();
    expect(screen.queryByText("图表序列加载中")).not.toBeInTheDocument();
  });

  it("renders yield curve points without requesting a time-series endpoint", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroYieldCurveModuleFixture()}
        moduleId="rates/yield-curve"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/rates/yield-curve" },
    );

    const points = screen.getAllByTestId("macro-yield-curve-point");
    expect(points.map((point) => point.textContent)).toEqual([
      "2年期美债收益率3.8%",
      "5年期美债收益率4%",
      "10年期美债收益率4.2%",
      "30年期美债收益率4.7%",
    ]);
    expect(apiMock.readApi).not.toHaveBeenCalledWith(
      "/api/macro/series",
      expect.objectContaining({ token: "test-token" }),
    );
    expectRegionsInOrder(["利率简报", "关键事实", "利率主图", "决策支持", "数据诊断"]);
  });
});

function expectRegionsInOrder(regionNames: string[]): void {
  const regionIndexes = regionNames.map((name) =>
    screen.getAllByRole("region").findIndex((region) => region.getAttribute("aria-label") === name),
  );
  expect(regionIndexes).not.toContain(-1);
  expect(regionIndexes).toEqual([...regionIndexes].sort((left, right) => left - right));
}

function expectRegionsInOrderWithin(container: HTMLElement, regionNames: string[]): void {
  const regions = within(container).getAllByRole("region");
  const regionIndexes = regionNames.map((name) =>
    regions.findIndex((region) => region.getAttribute("aria-label") === name),
  );
  expect(regionIndexes).not.toContain(-1);
  expect(regionIndexes).toEqual([...regionIndexes].sort((left, right) => left - right));
}

function assetDashboardTable({
  includeDate = true,
  includeMissingLatestRow = false,
  includeSource = true,
}: {
  includeDate?: boolean;
  includeMissingLatestRow?: boolean;
  includeSource?: boolean;
} = {}) {
  const row = (
    rowId: string,
    symbol: string,
    name: string,
    latest: string,
    delta: string,
    date = "2026-05-20",
  ) => ({
    row_id: rowId,
    cells: {
      indicator: { display_value: name, sort_value: symbol },
      symbol: { display_value: symbol, sort_value: symbol },
      latest: { display_value: latest, sort_value: Number.parseFloat(latest.replace(/,/g, "")) },
      delta_1d: { display_value: delta, sort_value: Number.parseFloat(delta) },
      delta_20d: { display_value: delta, sort_value: Number.parseFloat(delta) },
      ...(includeDate ? { observed_at: { display_value: date, sort_value: date } } : {}),
      ...(includeSource ? { source: { display_value: "fixture", sort_value: "fixture" } } : {}),
    },
  });

  return {
    id: "asset_group_snapshot",
    title: "大类资产快照",
    status: "ok",
    columns: [
      { key: "symbol", label: "代码" },
      { key: "indicator", label: "名称" },
      { key: "latest", label: "最新" },
      { key: "delta_1d", label: "日涨跌幅" },
      { key: "observed_at", label: "日期" },
      ...(includeSource ? [{ key: "source", label: "来源" }] : []),
    ],
    rows: [
      row("asset:spx", "^GSPC", "标普500", "5,312.40", "+0.30"),
      ...(includeMissingLatestRow ? [row("asset:iwm", "IWM", "罗素2000", "", "-0.42")] : []),
      row("asset:tlt", "TLT", "20年+国债ETF", "84.62", "-0.52"),
      row("commodity:gold", "GC", "黄金", "2,330.10", "+0.49"),
      row("fx:dxy", "DXY", "美元指数", "99.97", "-0.10"),
      row("crypto:btc", "BTC", "比特币", "68,300.00", "-0.76"),
    ],
  };
}

function assetAvailabilityTable(rows: Array<Record<string, unknown>> = []) {
  return {
    id: "availability_proxy_notes",
    title: "数据可用性 / 代理说明",
    status: "partial",
    columns: [
      { key: "item", label: "项目" },
      { key: "status", label: "状态" },
      { key: "latest", label: "最新观测" },
      { key: "coverage", label: "历史覆盖" },
      { key: "notes", label: "说明" },
    ],
    rows,
  };
}
