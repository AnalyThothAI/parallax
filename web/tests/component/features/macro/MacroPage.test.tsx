import { MacroPage } from "@features/macro";
import { screen, waitFor } from "@testing-library/react";
import {
  macroCorrelationFixture,
  macroModuleFixture,
  macroSeriesFixture,
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

describe("MacroPage compatibility wrapper", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/modules/overview") {
          return ok(
            macroModuleFixture({
              snapshot: {
                ...macroModuleFixture().snapshot,
                module_id: "overview",
                route_path: "/macro",
                section: "overview",
                title: "Overview",
              },
            }),
          );
        }
        if (path === "/api/macro/modules/assets/equities") {
          return ok(macroModuleFixture());
        }
        if (path === "/api/macro/series") {
          return ok(macroSeriesFixture(String(options?.params?.concept_keys ?? "").split(",")));
        }
        if (path === "/api/macro/assets/correlation") {
          return ok(macroCorrelationFixture());
        }
        throw new Error(`unexpected path ${path} ${JSON.stringify(options)}`);
      };
    });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the backend overview module through the new module API", async () => {
    renderWithProviders(<MacroPage token="test-token" />, { route: "/macro" });

    expect(await screen.findByRole("heading", { name: "宏观" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/overview", {
        token: "test-token",
      }),
    );
  });

  it("maps legacy module and section props to backend module ids", async () => {
    renderWithProviders(<MacroPage moduleId="assets" sectionId="equities" token="test-token" />, {
      route: "/macro/assets/equities",
    });

    expect(await screen.findByRole("heading", { name: "美股" })).toBeInTheDocument();
    expect(screen.getByText("Backend says equity leadership is constructive.")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/modules/assets/equities", {
        token: "test-token",
      }),
    );
  });

  it("keeps the legacy correlation escape hatch on the existing detail page", async () => {
    const onRouteChange = vi.fn();
    renderWithProviders(
      <MacroPage
        moduleId="assets"
        sectionId="correlation"
        token="test-token"
        onRouteChange={onRouteChange}
      />,
      { route: "/macro/assets/correlation" },
    );

    expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(await screen.findByText("SPY / QQQ")).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "test-token",
      }),
    );
  });
});
