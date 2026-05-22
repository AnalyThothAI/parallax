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
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/series", {
        params: { concept_keys: "asset:spx", window: "60d" },
        token: "test-token",
      }),
    );
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
      "2Y3.8%",
      "5Y4%",
      "10Y4.2%",
      "30Y4.7%",
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
    expect(within(cexBoard).getByText("12,500,000,000")).toBeInTheDocument();
    expect(screen.queryByText("暂无表格行")).not.toBeInTheDocument();
    expect(screen.getAllByRole("table", { name: "CEX 永续看板" })).toHaveLength(1);
    expect(screen.getByText("coinglass_partial")).toBeInTheDocument();
    expect(screen.getByText("basis_missing")).toBeInTheDocument();
    expect(screen.getByText("crypto_options_missing")).toBeInTheDocument();
    expect(screen.getByText("etf_flows_missing")).toBeInTheDocument();
    await screen.findByText("10%");
  });
});
