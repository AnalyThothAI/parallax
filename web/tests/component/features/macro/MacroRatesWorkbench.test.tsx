import { MacroWorkbenchRoute } from "@features/macro/MacroWorkbenchRoute";
import { MacroModulePageRenderer } from "@features/macro/ui/pages/MacroModulePageRenderer";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import {
  macroAuctionsProxyModuleFixture,
  macroExpectationsProxyModuleFixture,
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
  "市场解读",
  "关键事实",
  "主要图表",
  "决策支持",
  "利率明细",
  "利率数据诊断",
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
    module: macroAuctionsProxyModuleFixture(),
    moduleId: "rates/auctions" as const,
    route: "/macro/rates/auctions",
  },
  {
    module: macroRealRatesModuleFixture(),
    moduleId: "rates/real-rates" as const,
    route: "/macro/rates/real-rates",
  },
  {
    module: macroExpectationsProxyModuleFixture(),
    moduleId: "rates/expectations" as const,
    route: "/macro/rates/expectations",
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

  it("shows auction proxy copy without leaking raw auction codes", async () => {
    renderRatesModule(macroAuctionsProxyModuleFixture(), "rates/auctions", "/macro/rates/auctions");

    const marketRead = screen.getByRole("region", { name: "市场解读" });
    expect(within(marketRead).getAllByText(/当前为拍卖代理页面/).length).toBeGreaterThan(0);
    expect(
      within(screen.getByRole("region", { name: "主要图表" })).queryByText("暂无"),
    ).not.toBeInTheDocument();
    expect(marketRead).not.toHaveTextContent("treasury_auction");
    expect(
      (await within(screen.getByRole("region", { name: "主要图表" })).findAllByText("110%")).length,
    ).toBeGreaterThan(0);
  });

  it("shows expectations proxy copy without leaking raw policy-path codes", () => {
    renderRatesModule(
      macroExpectationsProxyModuleFixture(),
      "rates/expectations",
      "/macro/rates/expectations",
    );

    const marketRead = screen.getByRole("region", { name: "市场解读" });
    expect(within(marketRead).getAllByText(/当前为政策路径代理页面/).length).toBeGreaterThan(0);
    expect(marketRead).not.toHaveTextContent("fomc_probability_feed_missing");
  });

  it("renders the fed funds corridor band and EFFR line", async () => {
    renderRatesModule(macroFedFundsModuleFixture(), "rates/fed-funds", "/macro/rates/fed-funds");

    expect(await screen.findByTestId("rates-corridor-band")).toBeInTheDocument();
    expect(screen.getByTestId("rates-corridor-line-effr")).toBeInTheDocument();
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
        /macro_module_view_v3|source_snapshot_id|rates:dgs|fed:effr|fed_funds_futures_missing|fomc_probability_feed_missing|treasury_auction_(calendar|results)_missing|[{}]/,
      );
    },
  );

  it("uses a rates-specific route header without exposing projection version", async () => {
    renderWithProviders(
      <MacroWorkbenchRoute
        moduleId="rates/fed-funds"
        pageKind="leaf"
        productTier="primary"
        token="test-token"
      />,
      { route: "/macro/rates/fed-funds" },
    );

    expect(await screen.findByText("利率工作台")).toBeInTheDocument();
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
  return text.split("利率数据诊断")[0] ?? text;
}
