import { MacroAssetCorrelationPage } from "@features/macro";
import type { MacroAssetCorrelationData } from "@lib/types";
import { screen, waitFor } from "@testing-library/react";
import { ok } from "@tests/msw/fixtures";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { apiMock, setupAppRouteTest } from "@tests/routes/routeTestSetup";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

describe("MacroAssetCorrelationPage", () => {
  beforeEach(() => {
    setupAppRouteTest((mock) => {
      mock.getApiImpl = async (path, options) => {
        if (path === "/api/macro/assets/correlation") {
          expect(options?.params).toEqual({ window: "60d" });
          return ok(correlationFixture());
        }
        throw new Error(`unexpected path ${path}`);
      };
    });
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders backend-fed matrix, strongest pairs, and data gaps", async () => {
    renderWithProviders(<MacroAssetCorrelationPage token="test-token" />);

    expect(await screen.findByRole("heading", { name: "资产相关性" })).toBeInTheDocument();
    expect(await screen.findByRole("columnheader", { name: "SPY" })).toBeInTheDocument();
    expect(await screen.findByRole("rowheader", { name: "QQQ" })).toBeInTheDocument();
    expect(screen.getByText("SPY / QQQ")).toBeInTheDocument();
    expect(screen.getByText("+0.92")).toBeInTheDocument();
    expect(screen.getByText("SPY / TLT")).toBeInTheDocument();
    expect(screen.getAllByText("-0.61").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Yahoo").length).toBeGreaterThan(0);
    expect(screen.getByText("重叠样本不足：ETH / TLT")).toBeInTheDocument();
    expect(screen.queryByText(/insufficient_overlap/)).not.toBeInTheDocument();
    expect(screen.queryByText(/asset:spy|asset:qqq|asset:tlt|crypto:eth|yahoo/)).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMock.readApi).toHaveBeenCalledWith("/api/macro/assets/correlation", {
        params: { window: "60d" },
        token: "test-token",
      }),
    );
  });
});

export function correlationFixture(): MacroAssetCorrelationData {
  return {
    window: "60d",
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
