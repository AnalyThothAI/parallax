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
    expectRegionsInOrder(["宏观总览", "核心驱动", "全局传导链", "数据健康"]);
    const overview = screen.getByRole("region", { name: "宏观总览" });
    expect(within(overview).getByText("总览：风险偏好等待利率与流动性确认")).toBeInTheDocument();
    expect(within(overview).getAllByText("风险偏好部分确认").length).toBeGreaterThan(0);
    expect(within(overview).getByText("中低置信度")).toBeInTheDocument();
    expect(within(overview).getByText("加密 beta 需要美元流动性配合。")).toBeInTheDocument();
    const drivers = screen.getByRole("region", { name: "核心驱动" });
    expect(within(drivers).getByRole("table", { name: "美股代理快照" })).toBeInTheDocument();
    const dataHealth = screen.getByRole("region", { name: "数据健康" });
    expect(within(dataHealth).getByText("部分全局历史待回填")).toBeInTheDocument();
    expect(within(dataHealth).getByText("未来宏观日历待接入")).toBeInTheDocument();
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

    const overview = screen.getByRole("region", { name: "宏观总览" });
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
    expectRegionsInOrder([
      "关键指标",
      "市场板",
      "模块判断",
      "传导链",
      "模块证据",
      "数据来源",
      "模块数据健康",
    ]);
    expect(screen.getByRole("region", { name: "市场板" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块判断" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "传导链" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块证据" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "模块数据健康" })).toBeInTheDocument();
    expect(screen.queryByText("缺少 SRF")).not.toBeInTheDocument();
    expect(screen.getByText("Yahoo")).toBeInTheDocument();
    expect(screen.getByText("美股风险偏好")).toBeInTheDocument();
    expect(await screen.findByText("10%")).toBeInTheDocument();
  });

  it("renders assets landing as a terminal index", () => {
    renderWithProviders(
      <MacroModulePageRenderer
        module={macroAssetsModuleFixture()}
        moduleId="assets"
        pageKind="index"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    expect(screen.getByRole("region", { name: "大类资产索引" })).toBeInTheDocument();
    expect(screen.getByText("6 个板块")).toBeInTheDocument();
    expect(screen.getByText("4 个待确认")).toBeInTheDocument();
    const matrix = screen.getByRole("table", { name: "大类资产矩阵" });
    expect(
      within(matrix).getByRole("row", { name: /美股 历史不足 SPX \/ QQQ \/ IWM 等待小盘确认/ }),
    ).toBeInTheDocument();
    expect(
      within(matrix).getByRole("row", { name: /债券 曲线待确认 2Y \/ 10Y \/ 30Y/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看美股" })).toHaveAttribute(
      "href",
      "/macro/assets/equities",
    );
    expect(screen.queryByRole("region", { name: "模块判断" })).not.toBeInTheDocument();
  });

  it("derives asset index proxy and readings from backend section board rows", () => {
    const module = macroAssetsModuleFixture();
    module.section_boards = [
      {
        id: "equities",
        title: "美股",
        href: "/macro/assets/equities",
        status: "ok",
        status_label: "可用",
        rows: [
          {
            concept_key: "asset:spx",
            label: "标普500",
            short_label: "SPX",
            status: "ok",
            display_value: "5,312.40",
          },
          {
            concept_key: "asset:qqq",
            label: "纳指100 ETF",
            short_label: "QQQ",
            status: "ok",
            display_value: "451.10",
          },
          {
            concept_key: "asset:iwm",
            label: "罗素小盘",
            short_label: "IWM",
            status: "missing",
            display_value: null,
          },
        ],
      },
    ];

    renderWithProviders(
      <MacroModulePageRenderer
        module={module}
        moduleId="assets"
        pageKind="index"
        token="test-token"
      />,
      { route: "/macro/assets" },
    );

    const matrix = screen.getByRole("table", { name: "大类资产矩阵" });
    expect(
      within(matrix).getByRole("row", {
        name: /美股 可用 SPX \/ QQQ \/ IWM SPX 5,312\.40 \/ QQQ 451\.10/,
      }),
    ).toBeInTheDocument();
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
    const dataHealth = screen.getByRole("region", { name: "模块数据健康" });
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
