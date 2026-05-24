import {
  MacroAssetClassPage,
  MacroCryptoDerivativesPage,
  MacroOverviewPage,
  MacroRatesPage,
} from "@features/macro";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import {
  macroCryptoDerivativesModuleFixture,
  macroModuleFixture,
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
      <MacroOverviewPage module={macroModuleFixture()} moduleId="overview" token="test-token" />,
      { route: "/macro" },
    );

    expect(screen.getByLabelText("总览模块页面")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "当前解读" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "核心图表" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "支撑表格" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "证据板" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "数据源" })).toBeInTheDocument();
    const currentRead = screen.getByRole("region", { name: "当前解读" });
    expect(within(currentRead).getByText("美股风险：等待小盘确认")).toBeInTheDocument();
    expect(within(currentRead).getByText("风险偏好部分可用")).toBeInTheDocument();
    expect(within(currentRead).getByText("低置信度")).toBeInTheDocument();
    expect(
      within(currentRead).getByText("美股代理有最新值，但历史样本不足，不能确认加密 beta。"),
    ).toBeInTheDocument();
    expect(within(currentRead).getByText("高 beta 山寨暴露等待更多历史确认。")).toBeInTheDocument();
    const kpiStrip = screen.getByRole("region", { name: "关键指标" });
    expect(within(kpiStrip).getByText("标普500")).toBeInTheDocument();
    expect(within(kpiStrip).getByText("观测于 2026-05-20")).toBeInTheDocument();
    const evidence = screen.getByRole("region", { name: "证据板" });
    expect(within(evidence).getByRole("group", { name: "确认" })).toHaveTextContent(
      "SPX 最新值可用Yahoo 最新观测存在",
    );
    expect(within(evidence).getByRole("group", { name: "反证" })).toHaveTextContent(
      "IWM 样本不足小盘确认不足",
    );
    expect(within(evidence).getByRole("group", { name: "观察触发" })).toHaveTextContent(
      "60日历史补齐核心代理达到最小样本",
    );
    expect(within(evidence).getByRole("group", { name: "失效条件" })).toHaveTextContent(
      "SPX 跌破趋势风险偏好走弱",
    );
    const provenance = screen.getByRole("region", { name: "数据源" });
    expect(within(provenance).getByText("计分排除")).toBeInTheDocument();
    expect(screen.queryByText("insufficient_history")).not.toBeInTheDocument();
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
      <MacroOverviewPage
        module={macroModuleFixture({
          read: {
            headline: "",
            regime_label: "期限溢价压力",
            confidence_label: "中等置信度",
            trade_map: {},
          },
        })}
        moduleId="overview"
        token="test-token"
      />,
      { route: "/macro" },
    );

    const currentRead = screen.getByRole("region", { name: "当前解读" });
    expect(within(currentRead).getAllByText("期限溢价压力").length).toBeGreaterThan(0);
    expect(within(currentRead).queryByText("{}")).not.toBeInTheDocument();
    expect(within(currentRead).queryByText("暂无")).not.toBeInTheDocument();
    expect(currentRead).not.toHaveTextContent("term_premium_pressure");
  });

  it("renders asset-class normalized return page from backend payloads", async () => {
    renderWithProviders(
      <MacroAssetClassPage
        module={macroModuleFixture()}
        moduleId="assets/equities"
        token="test-token"
      />,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByLabelText("美股模块页面")).toBeInTheDocument();
    expect(await screen.findByText("10%")).toBeInTheDocument();
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
      <MacroAssetClassPage
        module={macroModuleFixture()}
        moduleId="assets/equities"
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
      <MacroRatesPage
        module={macroYieldCurveModuleFixture()}
        moduleId="rates/yield-curve"
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
      <MacroCryptoDerivativesPage
        module={macroCryptoDerivativesModuleFixture()}
        moduleId="assets/crypto-derivatives"
        token="test-token"
      />,
      { route: "/macro/assets/crypto-derivatives" },
    );

    const cexBoard = screen.getByRole("region", { name: "CEX 永续看板" });
    expect(within(cexBoard).getByText("12.50B")).toBeInTheDocument();
    expect(screen.queryByText("暂无表格行")).not.toBeInTheDocument();
    expect(screen.getAllByRole("table", { name: "CEX 永续看板" })).toHaveLength(1);
    expect(screen.getByText("Coinglass 数据不完整")).toBeInTheDocument();
    expect(screen.getByText("基差数据缺失")).toBeInTheDocument();
    expect(screen.getByText("加密期权数据缺失")).toBeInTheDocument();
    expect(screen.getByText("ETF 资金流缺失")).toBeInTheDocument();
    expect(screen.queryByText("coinglass_partial")).not.toBeInTheDocument();
    expect(screen.queryByText("basis_missing")).not.toBeInTheDocument();
    expect(screen.queryByText("crypto_options_missing")).not.toBeInTheDocument();
    expect(screen.queryByText("etf_flows_missing")).not.toBeInTheDocument();
    await screen.findByText("10%");
  });
});
