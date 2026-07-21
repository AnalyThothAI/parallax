import { MacroWorkbenchRoute } from "@features/macro/MacroWorkbenchRoute";
import { MacroModulePageRenderer } from "@features/macro/ui/pages/MacroModulePageRenderer";
import type { MacroModuleTable } from "@lib/types";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import {
  macroFedFundsModuleFixture,
  macroRealRatesModuleFixture,
  macroSeriesFixture,
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

const RATES_REGIONS = [
  "利率页导航",
  "利率简报",
  "关键事实",
  "利率主图",
  "决策支持",
  "利率明细",
  "数据诊断",
];

const RATES_CASES = [
  {
    module: macroFedFundsModuleFixture(),
    moduleId: "rates/fed-funds" as const,
    route: "/macro/rates/fed-funds",
  },
  {
    module: macroYieldCurveModuleFixture(),
    moduleId: "rates/yield-curve" as const,
    route: "/macro/rates/yield-curve",
  },
  {
    module: macroRealRatesModuleFixture(),
    moduleId: "rates/real-rates" as const,
    route: "/macro/rates/real-rates",
  },
];

describe("Macro rates workbench", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/modules/rates/fed-funds") {
          return ok(macroFedFundsModuleFixture());
        }
        if (path === "/api/macro/series") {
          const conceptKeys = String(options?.params?.concept_keys ?? "fed:effr").split(",");
          return ok(macroSeriesFixture(conceptKeys));
        }
        throw new Error(`unexpected path ${path}`);
      };
    });
  });

  afterEach(() => {
    cleanup();
  });

  it.each(RATES_CASES)(
    "renders $moduleId regions in rates-workbench order",
    ({ module, moduleId, route }) => {
      renderRatesModule(module, moduleId, route);

      expectRegionsInOrder(RATES_REGIONS);
    },
  );

  it("keeps the rates read compact and removes prompt-style copy", () => {
    renderRatesModule(macroFedFundsModuleFixture(), "rates/fed-funds", "/macro/rates/fed-funds");

    const marketRead = screen.getByRole("region", { name: "利率简报" });
    expect(within(marketRead).getByText("状态")).toBeInTheDocument();
    expect(within(marketRead).getByText("缺口")).toBeInTheDocument();
    expect(within(marketRead).queryByText("问题")).not.toBeInTheDocument();
    expect(marketRead).not.toHaveTextContent("政策走廊是否稳定");
    expect(marketRead).not.toHaveTextContent("本页只展示");
    expect(within(marketRead).queryByText("联邦基金与走廊")).not.toBeInTheDocument();
  });

  it("removes the rates fact strip when no facts exist", () => {
    const module = { ...macroFedFundsModuleFixture(), tiles: [] };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "关键事实" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无关键事实")).not.toBeInTheDocument();
  });

  it("uses backend module title for the rates page scaffold label", () => {
    renderRatesModule(macroFedFundsModuleFixture(), "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.getByRole("region", { name: "联邦基金与走廊模块页面" })).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "联邦基金与走廊利率工作台" }),
    ).not.toBeInTheDocument();
  });

  it("omits missing rates fact metadata instead of placeholder copy", () => {
    const base = macroFedFundsModuleFixture();
    const module = {
      ...base,
      tiles: [
        {
          ...base.tiles[0],
          observed_at: null,
          observed_at_label: null,
          quality: null,
          quality_label: null,
          source_label: null,
        },
      ],
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const facts = screen.getByRole("region", { name: "关键事实" });
    expect(facts).not.toHaveTextContent("暂无来源");
    expect(facts).not.toHaveTextContent("暂无日期");
    expect(facts).not.toHaveTextContent("暂无状态");
  });

  it("omits missing rates read dates instead of placeholder copy", () => {
    const base = macroFedFundsModuleFixture();
    const module = {
      ...base,
      snapshot: {
        ...base.snapshot,
        asof_date: null,
        asof_label: null,
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const marketRead = screen.getByRole("region", { name: "利率简报" });
    expect(marketRead).not.toHaveTextContent("暂无日期");
    expect(within(marketRead).queryByText("截至")).not.toBeInTheDocument();
  });

  it("omits empty rates readiness status fields without frontend status labels", () => {
    const base = macroFedFundsModuleFixture();
    const module = {
      ...base,
      data_health: {
        ...base.data_health,
        summary_label: "",
        summary_status: "stale",
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const marketRead = screen.getByRole("region", { name: "利率简报" });
    expect(within(marketRead).queryByText("状态")).not.toBeInTheDocument();
    expect(marketRead).not.toHaveTextContent("已过期");
  });

  it("removes empty rates diagnostics buckets and source table", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      data_health: {
        summary_label: "利率数据可用",
        summary_status: "ok",
        module_gaps: [],
        chart_gaps: [],
        global_gaps: [],
      },
      provenance: { rows: [] },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    expect(diagnostics).not.toHaveTextContent("暂无");
    expect(within(diagnostics).queryByText("来源状态")).not.toBeInTheDocument();
    expect(
      within(diagnostics).queryByRole("table", { name: "利率数据源" }),
    ).not.toBeInTheDocument();
    expect(within(diagnostics).queryByText("暂无数据源元信息")).not.toBeInTheDocument();
  });

  it("does not translate rates gap severity codes into diagnostics text", () => {
    const base = macroFedFundsModuleFixture();
    const module = {
      ...base,
      data_health: {
        ...base.data_health,
        module_gaps: [
          {
            code: "sofr_30d_missing",
            label: "SOFR 30D 尚未入库",
            severity: "warning",
          },
        ],
        chart_gaps: [],
        global_gaps: [],
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    expect(within(diagnostics).getByText("SOFR 30D 尚未入库")).toBeInTheDocument();
    expect(within(diagnostics).queryByText("警告")).not.toBeInTheDocument();
  });

  it("does not manufacture rates source diagnostics labels from source counts", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      provenance: {
        rows: [{ row_id: "source:fred" }],
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    expect(within(diagnostics).queryByText("1 个来源")).not.toBeInTheDocument();
    expect(within(diagnostics).queryByText("来源状态")).not.toBeInTheDocument();
  });

  it("removes rates decision support when evidence groups are empty", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      module_evidence: {
        confirmations: [],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "决策支持" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无")).not.toBeInTheDocument();
  });

  it("removes rates market read when backend headline is absent", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      module_read: {
        ...macroFedFundsModuleFixture().module_read,
        headline: null,
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "利率简报" })).not.toBeInTheDocument();
    expect(screen.queryByText(/政策利率走廊：/)).not.toBeInTheDocument();
  });

  it("removes rates detail tables when no primary rows exist", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      tables: [],
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "利率明细" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无利率明细")).not.toBeInTheDocument();
  });

  it("removes rates detail tables without backend table ids and titles", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      tables: [
        {
          columns: [{ key: "value", label: "值" }],
          rows: [
            {
              row_id: "rates:effr",
              cells: { value: { display_value: "99.99%", sort_value: 99.99 } },
            },
          ],
        } as unknown as MacroModuleTable,
        {
          id: "missing_title",
          columns: [{ key: "value", label: "值" }],
          rows: [
            {
              row_id: "rates:sofr",
              cells: { value: { display_value: "88.88%", sort_value: 88.88 } },
            },
          ],
        },
      ],
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "利率明细" })).not.toBeInTheDocument();
    expect(screen.queryByText("99.99%")).not.toBeInTheDocument();
    expect(screen.queryByText("88.88%")).not.toBeInTheDocument();
  });

  it("removes the rates primary visual when the backend has no chart series", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      primary_chart: { id: "fed_funds_corridor", missing_concept_keys: [], series: [] },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "利率主图" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无可绘制走廊数据")).not.toBeInTheDocument();
  });

  it("removes the rates primary visual when corridor series are not renderable after model filtering", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      primary_chart: {
        id: "fed_funds_corridor",
        missing_concept_keys: [],
        series: [{ concept_key: "rates:unknown_proxy", label: "未知代理" }],
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    expect(screen.queryByRole("region", { name: "利率主图" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无可绘制走廊数据")).not.toBeInTheDocument();
    expect(screen.queryByText("未知代理")).not.toBeInTheDocument();
  });

  it("does not use rates readiness as primary-chart meta when chart copy is absent", () => {
    const base = macroFedFundsModuleFixture();
    const module = {
      ...base,
      primary_chart: {
        ...base.primary_chart,
        subtitle: null,
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const primaryVisual = screen.getByRole("region", { name: "利率主图" });
    expect(within(primaryVisual).queryByText("走廊数据部分可用")).not.toBeInTheDocument();
    expect(
      within(primaryVisual).queryByText("目标区间、EFFR、IORB 与 SOFR"),
    ).not.toBeInTheDocument();
  });

  it("omits missing rates decision details instead of placeholder copy", () => {
    const module = {
      ...macroFedFundsModuleFixture(),
      module_evidence: {
        confirmations: [{ label: "EFFR 可用" }],
        contradictions: [],
        watch_triggers: [],
        invalidations: [],
      },
    };

    renderRatesModule(module, "rates/fed-funds", "/macro/rates/fed-funds");

    const decisionSupport = screen.getByRole("region", { name: "决策支持" });
    expect(within(decisionSupport).getByText("EFFR 可用")).toBeInTheDocument();
    expect(decisionSupport).not.toHaveTextContent("暂无");
  });

  it("renders the fed funds corridor band and EFFR line", async () => {
    renderRatesModule(macroFedFundsModuleFixture(), "rates/fed-funds", "/macro/rates/fed-funds");

    expect(await screen.findByTestId("rates-corridor-band")).toBeInTheDocument();
    expect(screen.getByTestId("rates-corridor-line-effr")).toBeInTheDocument();
    expect(screen.getByText("缺少指标：SOFR 30D")).toBeInTheDocument();
    expect(screen.queryByText(/待补齐/)).not.toBeInTheDocument();
  });

  it("renders fed funds policy diagnostics between chart and decision support", () => {
    renderRatesModule(macroFedFundsModuleFixture(), "rates/fed-funds", "/macro/rates/fed-funds");

    const ratesNavigation = screen.getByRole("navigation", { name: "利率模块" });
    expect(
      within(ratesNavigation).queryByRole("link", { name: "政策预期" }),
    ).not.toBeInTheDocument();

    expectRegionsInOrder([
      "利率页导航",
      "利率简报",
      "关键事实",
      "利率主图",
      "政策走廊诊断",
      "决策支持",
      "利率明细",
      "数据诊断",
    ]);

    const diagnostics = screen.getByRole("region", { name: "政策走廊诊断" });
    expect(within(diagnostics).getByText("政策走廊诊断 · 走廊压力")).toBeInTheDocument();
    expect(within(diagnostics).getByText("EFFR-IORB")).toBeInTheDocument();
    expect(within(diagnostics).getByText("15bp · 1w +20bp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("OBFR-EFFR")).toBeInTheDocument();
    expect(within(diagnostics).getByText("$102B · 1w -$43B")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "走廊压力：降低融资敏感资产和杠杆多头，等待 EFFR 回到目标区间内。",
      ),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent(/fed:|liquidity:/);
  });

  it("renders yield curve diagnostics as a decision block", () => {
    renderRatesModule(
      macroYieldCurveModuleFixture(),
      "rates/yield-curve",
      "/macro/rates/yield-curve",
    );

    const diagnostics = screen.getByRole("region", { name: "曲线诊断" });
    expect(within(diagnostics).getByText("曲线诊断 · 熊陡")).toBeInTheDocument();
    expect(within(diagnostics).getByText("2s10s")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("40bp · 1w +10bp · 1m +10bp · 3m +10bp"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("期限溢价压力：优先防守长久期成长、长债和高 beta。"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("若 10Y 回落且 2s10s 重新走平，曲线压力降级。"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("历史利差")).toBeInTheDocument();
    expect(within(diagnostics).getByText("30bp 至 40bp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("2026-05-20：40bp")).toBeInTheDocument();
    expect(within(diagnostics).getByText("期限拆分")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("名义 4% · 实际 2.1% · 通胀补偿 1.9%"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("1w：名义 +10bp · 实际 +15bp · 通胀补偿 -5bp"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("残差 0bp")).toBeInTheDocument();
  });

  it("renders real rate diagnostics as a decision block", () => {
    renderRatesModule(macroRealRatesModuleFixture(), "rates/real-rates", "/macro/rates/real-rates");

    const diagnostics = screen.getByRole("region", { name: "实际利率诊断" });
    expect(within(diagnostics).getByText("实际利率诊断 · 实际利率压力")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText(
        "实际利率上行且通胀补偿未同步走阔：估值压力偏实际利率驱动，长久期与高 beta 需要降级。",
      ),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("5Y Real")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("2.05% · 1w +20bp · 1m +35bp · 3m +45bp"),
    ).toBeInTheDocument();
    expect(within(diagnostics).getByText("10Y Breakeven")).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("2.15% · 1w -5bp · 1m -10bp · 3m -5bp"),
    ).toBeInTheDocument();
    expect(
      within(diagnostics).getByText("实际利率压力：降低长久期成长、长债和高 beta 反弹置信度。"),
    ).toBeInTheDocument();
    expect(diagnostics).not.toHaveTextContent(/rates:|inflation:/);
  });

  it.each(RATES_CASES)(
    "keeps $moduleId primary text free of backend ids before diagnostics",
    async ({ module, moduleId, route }) => {
      const { container } = renderRatesModule(module, moduleId, route);

      if (moduleId === "rates/fed-funds") {
        expect(await screen.findByTestId("rates-corridor-line-effr")).toBeInTheDocument();
      } else if (moduleId !== "rates/yield-curve") {
        await waitFor(() => expect(screen.queryByText("图表序列加载中")).not.toBeInTheDocument());
      }

      const primaryText = textBeforeDiagnostics(container);
      expect(primaryText).not.toMatch(
        /macro_module_view_v3|rates:dgs|fed:effr|fed_funds_futures_missing|fomc_probability_feed_missing|[{}]/,
      );
    },
  );

  it("omits local rates shell eyebrow copy without exposing projection version", async () => {
    renderWithProviders(
      <MacroWorkbenchRoute
        moduleId="rates/fed-funds"
        pageKind="leaf"
        productTier="primary"
        token="test-token"
      />,
      { route: "/macro/rates/fed-funds" },
    );

    expect(await screen.findByRole("heading", { name: "政策利率走廊" })).toBeInTheDocument();
    expect(screen.queryByText("利率工作台")).not.toBeInTheDocument();
    const state = screen.getByLabelText("页面状态");
    expect(within(state).getByText("数据")).toBeInTheDocument();
    expect(within(state).getByText("截至")).toBeInTheDocument();
    expect(within(state).queryByText("版本")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/rates/fed-funds", {
        token: "test-token",
      }),
    );
  });
});

function renderRatesModule(
  module: (typeof RATES_CASES)[number]["module"],
  moduleId: (typeof RATES_CASES)[number]["moduleId"],
  route: string,
) {
  return renderWithProviders(
    <MacroModulePageRenderer
      module={module}
      moduleId={moduleId}
      pageKind="leaf"
      token="test-token"
    />,
    { route },
  );
}

function expectRegionsInOrder(regionNames: string[]): void {
  const regionIndexes = regionNames.map((name) =>
    screen.getAllByRole("region").findIndex((region) => region.getAttribute("aria-label") === name),
  );
  expect(regionIndexes).not.toContain(-1);
  expect(regionIndexes).toEqual([...regionIndexes].sort((left, right) => left - right));
}

function textBeforeDiagnostics(container: HTMLElement): string {
  const text = container.textContent ?? "";
  return text.split("数据诊断")[0] ?? text;
}
