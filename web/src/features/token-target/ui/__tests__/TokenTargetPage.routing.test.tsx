import { setAuthToken } from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { createApiMock, ok, resetApiMock } from "../../../../test/msw/fixtures";
import { apiHandlers } from "../../../../test/msw/handlers";
import { server } from "../../../../test/msw/server";
import { TokenTargetPage } from "../TokenTargetPage";

const apiMock = createApiMock();

beforeEach(() => {
  setAuthToken("test-token");
  resetApiMock(apiMock);
  server.use(...apiHandlers(apiMock));
});

afterEach(() => {
  setAuthToken(null);
});

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/token/:targetType/:targetId" element={<TokenTargetPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TokenTargetPage routing", () => {
  it("calls target-social-timeline with target_type and target_id from the URL", async () => {
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/target-posts") {
        return ok({
          items: [],
          returned_count: 0,
          total_count: 0,
          has_more: false,
          score_window: { window: "1h" },
          query: { sort: "recent" },
        } as any);
      }
      return ok({
        stages: [],
        posts: [],
        summary: { posts: 0, authors: 0 },
        targets: [],
        attention: [],
      } as any);
    };

    renderAt("/token/Asset/asset%3Apepe");

    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/target-social-timeline",
        expect.objectContaining({
          params: expect.objectContaining({
            target_type: "Asset",
            target_id: "asset:pepe",
          }),
        }),
      );
    });
  });

  it("renders an in-page 404 when targetType is not in {Asset, CexToken}", async () => {
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/target-posts") {
        return ok({
          items: [],
          returned_count: 0,
          total_count: 0,
          has_more: false,
          score_window: { window: "1h" },
          query: { sort: "recent" },
        } as any);
      }
      return ok({ targets: [], attention: [] });
    };

    const { container } = renderAt("/token/foo/bar");

    expect(container.textContent ?? "").toMatch(/不存在|失效|invalid/i);
    // Invalid target types must not fire a doomed timeline request.
    expect(
      apiMock.readApi.mock.calls.some(([path]) => path === "/api/target-social-timeline"),
    ).toBe(false);
  });

  it("renders an honest CEX target page when the current radar window has no row", async () => {
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/token-radar") {
        return ok({ targets: [], attention: [], projection: {} });
      }
      if (path === "/api/target-social-timeline") {
        return ok({
          summary: {
            posts: 0,
            authors: 0,
            effective_authors: 0,
            watched_posts: 0,
            phase: "seed",
            top_author_share: 0,
            latest_seen_ms: null,
          },
          market_overlay: { price_series_type: "anchor_line", candle_status: "missing_market_id" },
          stages: [],
          buckets: [],
          authors: [],
          posts: [],
          cascade: { edges: [], unresolved_parents: [] },
        } as any);
      }
      if (path === "/api/target-posts") {
        return ok({
          items: [],
          returned_count: 0,
          total_count: 0,
          has_more: false,
          score_window: { window: "1h" },
          query: {
            target_type: "CexToken",
            target_id: "cex_token:ZEC",
            window: "1h",
            scope: "all",
            range: "current_window",
            sort: "recent",
          },
        } as any);
      }
      return ok({});
    };

    const { container } = renderAt("/token/CexToken/cex_token%3AZEC");

    expect(await screen.findByRole("heading", { name: "$ZEC" })).toBeInTheDocument();
    expect(screen.getAllByText("Not in current radar window").length).toBeGreaterThan(0);
    expect(screen.queryByText("score audit")).not.toBeInTheDocument();
    expect(apiMock.readApi).toHaveBeenCalledWith(
      "/api/target-social-timeline",
      expect.objectContaining({
        params: expect.objectContaining({
          target_type: "CexToken",
          target_id: "cex_token:ZEC",
        }),
      }),
    );
    expect(screen.getByRole("heading", { name: "Social x Market Timeline" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("seeds the audit window from the URL query", async () => {
    apiMock.readApiImpl = async (path: string) => {
      if (path === "/api/target-posts") {
        return ok({
          items: [],
          returned_count: 0,
          total_count: 0,
          has_more: false,
          score_window: { window: "24h" },
          query: { sort: "recent" },
        } as any);
      }
      if (path === "/api/target-social-timeline") {
        return ok({ stages: [], posts: [], summary: { posts: 0, authors: 0 } } as any);
      }
      return ok({ targets: [], attention: [], projection: {} });
    };

    renderAt("/token/CexToken/cex_token%3AZEC?window=24h");

    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/token-radar",
        expect.objectContaining({
          params: expect.objectContaining({
            window: "24h",
          }),
        }),
      );
    });
  });
});
