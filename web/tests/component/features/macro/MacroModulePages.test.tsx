import { MacroModulePageRenderer } from "@features/macro/ui/pages/MacroModulePageRenderer";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import {
  macroAssetsModuleFixture,
  macroCryptoDerivativesModuleFixture,
  macroModuleFixture,
  macroOverviewModuleFixture,
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

    expect(screen.getByRole("region", { name: "总览模块页面" })).toHaveAttribute(
      "data-page-kind",
      "overview",
    );
    expect(document.querySelector(".macro-page-panel-current")).not.toBeInTheDocument();
    expectRegionsInOrder(["宏观简报", "跨域市场板", "传导链", "数据诊断"]);
    const overview = screen.getByRole("region", { name: "宏观简报" });
    expect(within(overview).getByText("总览：风险偏好等待利率与流动性确认")).toBeInTheDocument();
    expect(within(overview).getAllByText("风险偏好部分确认").length).toBeGreaterThan(0);
    expect(within(overview).getByText("中低置信度")).toBeInTheDocument();
    expect(within(overview).getByText("加密 beta 需要美元流动性配合。")).toBeInTheDocument();
    const drivers = screen.getByRole("region", { name: "跨域市场板" });
    expect(within(drivers).getByRole("table", { name: "美股代理快照" })).toBeInTheDocument();
    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(within(dataHealth).getByText("部分全局历史待回填")).toBeInTheDocument();
    expect(within(dataHealth).getByText("未来宏观日历待接入")).toBeInTheDocument();
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

    expect(screen.getByRole("region", { name: "美股模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["模块简报", "主市场证据", "驱动与反证", "数据诊断"]);
    expect(screen.getByRole("region", { name: "主市场证据" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块简报" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "驱动与反证" })).toBeInTheDocument();
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

  it("renders the asset landing page as a market board before supporting readouts", () => {
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

    expect(screen.getByRole("region", { name: "大类资产模块页面" })).toBeInTheDocument();
    expectRegionsInOrder(["核心资产行情", "今日判断", "数据诊断", "60日相关性"]);
    expect(screen.queryByRole("region", { name: "关键指标" })).not.toBeInTheDocument();

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
    ).toEqual(expect.arrayContaining(["代码", "名称", "最新", "20日变化", "日期"]));
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

  it("renders crypto derivatives CEX board source and explicit data gaps", async () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroCryptoDerivativesModuleFixture()}
        moduleId="assets/crypto-derivatives"
        pageKind="leaf"
        token="test-token"
      />,
      { route: "/macro/assets/crypto-derivatives" },
    );

    const cexBoard = screen.getByRole("table", { name: "CEX 永续看板" });
    expect(within(cexBoard).getByText("12.50B")).toBeInTheDocument();
    expect(screen.queryByText("暂无表格行")).not.toBeInTheDocument();
    expect(screen.getAllByRole("table", { name: "CEX 永续看板" })).toHaveLength(1);
    expectRegionsInOrder(["模块简报", "主市场证据", "驱动与反证", "数据诊断"]);
    const dataHealth = screen.getByRole("region", { name: "数据诊断" });
    expect(screen.getByText("Coinglass 数据不完整")).toBeInTheDocument();
    expect(within(dataHealth).getByText("基差数据缺失")).toBeInTheDocument();
    expect(within(dataHealth).getByText("加密期权数据缺失")).toBeInTheDocument();
    expect(within(dataHealth).getByText("ETF 资金流缺失")).toBeInTheDocument();
    expect(screen.queryByText("coinglass_partial")).not.toBeInTheDocument();
    expect(screen.queryByText("basis_missing")).not.toBeInTheDocument();
    expect(screen.queryByText("crypto_options_missing")).not.toBeInTheDocument();
    expect(screen.queryByText("etf_flows_missing")).not.toBeInTheDocument();
    await screen.findByText("10%");
  });
});

function expectRegionsInOrder(regionNames: string[]): void {
  const regionIndexes = regionNames.map((name) =>
    screen.getAllByRole("region").findIndex((region) => region.getAttribute("aria-label") === name),
  );
  expect(regionIndexes).not.toContain(-1);
  expect(regionIndexes).toEqual([...regionIndexes].sort((left, right) => left - right));
}

function assetDashboardTable() {
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
      observed_at: { display_value: date, sort_value: date },
      source: { display_value: "fixture", sort_value: "fixture" },
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
    ],
    rows: [
      row("asset:spx", "^GSPC", "标普500", "5,312.40", "+0.30"),
      row("asset:tlt", "TLT", "20年+国债ETF", "84.62", "-0.52"),
      row("commodity:gold", "GC", "黄金", "2,330.10", "+0.49"),
      row("fx:dxy", "DXY", "美元指数", "99.97", "-0.10"),
      row("crypto:btc", "BTC", "比特币", "68,300.00", "-0.76"),
    ],
  };
}
