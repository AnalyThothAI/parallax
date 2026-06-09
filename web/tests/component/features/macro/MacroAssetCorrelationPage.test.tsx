import { MacroMatrixPage } from "@features/macro";
import type { MacroAssetCorrelationData, MacroAssetCorrelationWindow } from "@lib/types";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { apiMock, setupAppRouteTest } from "@tests/routes/routeTestSetup";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

describe("MacroMatrixPage", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/assets/correlation") {
          const window = options?.params?.window;
          expect(["20d", "60d", "120d"]).toContain(window);
          return ok(correlationFixture(window as MacroAssetCorrelationWindow));
        }
        throw new Error(`unexpected path ${path}`);
      };
    });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the correlation matrix inside macro shell grammar", async () => {
    renderWithProviders(<MacroMatrixPage token="test-token" />, {
      route: "/macro/assets/correlation",
    });

    expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(screen.getByLabelText("宏观工作台")).toHaveAttribute("data-page-kind", "matrix");
    expect(screen.getByRole("navigation", { name: "宏观面包屑" })).toHaveTextContent(
      "宏观/大类资产/相关性",
    );
    expect(await screen.findByRole("region", { name: "相关性简报" })).toBeInTheDocument();
    expectRegionsInOrder(["相关性简报", "相关性证据", "数据诊断", "相关性矩阵"]);
    expect(screen.getByRole("button", { name: "20d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "60d" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("查看完整矩阵").closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByRole("table", { name: "60d 资产相关性矩阵" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("查看完整矩阵"));
    expect(await screen.findByRole("table", { name: "60d 资产相关性矩阵" })).toBeInTheDocument();
    expect(await screen.findByRole("columnheader", { name: "SPY" })).toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: "QQQ" })).toBeInTheDocument();
    expect(screen.getByText("SPY / QQQ")).toBeInTheDocument();
    expect(screen.getByText("+0.92")).toBeInTheDocument();
    expect(screen.getByText("SPY / TLT")).toBeInTheDocument();
    expect(screen.getAllByText("-0.61").length).toBeGreaterThan(0);
    const diagnostics = screen.getByRole("region", { name: "数据诊断" });
    expect(diagnostics).toHaveTextContent("Yahoo");
    expect(diagnostics).toHaveTextContent("重叠样本不足：ETH / TLT");
    expect(screen.queryByRole("region", { name: "最强正相关" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "最强负相关" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "覆盖度" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "数据缺口" })).not.toBeInTheDocument();
    expect(screen.queryByText(/insufficient_overlap/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/asset:spy|asset:qqq|asset:tlt|crypto:eth|yahoo/),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "test-token",
      }),
    );
  });

  it("switches the matrix window from the segmented header actions", async () => {
    renderWithProviders(<MacroMatrixPage token="test-token" />, {
      route: "/macro/assets/correlation",
    });

    expect(await screen.findByRole("region", { name: "相关性矩阵" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("查看完整矩阵"));
    expect(await screen.findByRole("table", { name: "60d 资产相关性矩阵" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "20d" }));

    expect(await screen.findByRole("table", { name: "20d 资产相关性矩阵" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "20d" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "60d" })).toHaveAttribute("aria-pressed", "false");
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "20d" },
        token: "test-token",
      }),
    );
  });
});

function expectRegionsInOrder(regionNames: string[]): void {
  const regionIndexes = regionNames.map((name) =>
    screen.getAllByRole("region").findIndex((region) => region.getAttribute("aria-label") === name),
  );
  expect(regionIndexes).not.toContain(-1);
  expect(regionIndexes).toEqual([...regionIndexes].sort((left, right) => left - right));
}

export function correlationFixture(
  window: MacroAssetCorrelationWindow = "60d",
): MacroAssetCorrelationData {
  return {
    window,
    asof_date: "2026-05-20",
    assets: [
      {
        concept_key: "asset:spy",
        title: "SPY",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
      {
        concept_key: "asset:qqq",
        title: "QQQ",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
      {
        concept_key: "asset:tlt",
        title: "TLT",
        observations_count: 64,
        return_count: 60,
        start_date: "2026-02-21",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
      {
        concept_key: "crypto:eth",
        title: "ETH",
        observations_count: 3,
        return_count: 2,
        start_date: "2026-05-18",
        end_date: "2026-05-20",
        latest_observed_at: "2026-05-20",
        sources: ["yahoo"],
      },
    ],
    matrix: [
      {
        concept_key: "asset:spy",
        correlations: {
          "asset:spy": 1,
          "asset:qqq": 0.92,
          "asset:tlt": -0.61,
          "crypto:eth": null,
        },
      },
      {
        concept_key: "asset:qqq",
        correlations: {
          "asset:spy": 0.92,
          "asset:qqq": 1,
          "asset:tlt": -0.42,
          "crypto:eth": null,
        },
      },
      {
        concept_key: "asset:tlt",
        correlations: {
          "asset:spy": -0.61,
          "asset:qqq": -0.42,
          "asset:tlt": 1,
          "crypto:eth": null,
        },
      },
      {
        concept_key: "crypto:eth",
        correlations: {
          "asset:spy": null,
          "asset:qqq": null,
          "asset:tlt": null,
          "crypto:eth": 1,
        },
      },
    ],
    pairs: [
      {
        left: "asset:spy",
        right: "asset:qqq",
        correlation: 0.92,
        sample_size: 58,
        start_date: "2026-02-24",
        end_date: "2026-05-20",
        available: true,
        reason: null,
      },
      {
        left: "asset:spy",
        right: "asset:tlt",
        correlation: -0.61,
        sample_size: 57,
        start_date: "2026-02-25",
        end_date: "2026-05-20",
        available: true,
        reason: null,
      },
      {
        left: "crypto:eth",
        right: "asset:tlt",
        correlation: null,
        sample_size: 2,
        start_date: null,
        end_date: null,
        available: false,
        reason: "insufficient_overlap",
      },
    ],
    data_gaps: [
      {
        code: "insufficient_overlap",
        left: "crypto:eth",
        right: "asset:tlt",
        sample_size: 2,
      },
    ],
  };
}
