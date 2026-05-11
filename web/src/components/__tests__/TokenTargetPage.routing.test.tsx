import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TokenTargetPage } from "../TokenTargetPage";
import * as client from "../../api/client";
import { useTraderStore } from "../../store/useTraderStore";

beforeEach(() => {
  useTraderStore.setState({ token: "test-token", scope: "all" });
});

afterEach(() => {
  vi.restoreAllMocks();
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
    </QueryClientProvider>
  );
}

describe("TokenTargetPage routing", () => {
  it("calls target-social-timeline with target_type and target_id from the URL", async () => {
    const getApi = vi.spyOn(client, "getApi").mockImplementation(async (path: string) => {
      if (path === "/api/target-posts") {
        return {
          ok: true,
          data: { items: [], returned_count: 0, total_count: 0, has_more: false, score_window: { window: "1h" }, query: { sort: "recent" } }
        } as any;
      }
      return { ok: true, data: { stages: [], posts: [], summary: { posts: 0, authors: 0 }, targets: [], attention: [] } } as any;
    });

    renderAt("/token/Asset/asset%3Apepe");

    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith(
        "/api/target-social-timeline",
        expect.objectContaining({
          params: expect.objectContaining({
            target_type: "Asset",
            target_id: "asset:pepe"
          })
        })
      );
    });
  });

  it("renders an in-page 404 when targetType is not in {Asset, CexToken}", async () => {
    const getApi = vi.spyOn(client, "getApi").mockImplementation(async (path: string) => {
      if (path === "/api/target-posts") {
        return {
          ok: true,
          data: { items: [], returned_count: 0, total_count: 0, has_more: false, score_window: { window: "1h" }, query: { sort: "recent" } }
        } as any;
      }
      return { ok: true, data: { targets: [], attention: [] } } as any;
    });

    const { container } = renderAt("/token/foo/bar");

    expect(container.textContent ?? "").toMatch(/不存在|失效|invalid/i);
    // Invalid target types must not fire a doomed timeline request.
    expect(getApi.mock.calls.some(([path]) => path === "/api/target-social-timeline")).toBe(false);
  });

  it("renders an honest CEX target page when the current radar window has no row", async () => {
    const getApi = vi.spyOn(client, "getApi").mockImplementation(async (path: string) => {
      if (path === "/api/token-radar") {
        return { ok: true, data: { targets: [], attention: [], projection: {} } } as any;
      }
      if (path === "/api/target-social-timeline") {
        return {
          ok: true,
          data: {
            stages: [],
            posts: [],
            summary: { posts: 0, authors: 0, effective_authors: 0, watched_posts: 0, phase: "seed" }
          }
        } as any;
      }
      if (path === "/api/target-posts") {
        return {
          ok: true,
          data: {
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
              sort: "recent"
            }
          }
        } as any;
      }
      return { ok: true, data: {} } as any;
    });

    renderAt("/token/CexToken/cex_token%3AZEC");

    expect(await screen.findByRole("heading", { name: "$ZEC" })).toBeInTheDocument();
    expect(screen.getAllByText("Not in current radar window").length).toBeGreaterThan(0);
    expect(screen.queryByText("score audit")).not.toBeInTheDocument();
    expect(getApi).toHaveBeenCalledWith(
      "/api/target-social-timeline",
      expect.objectContaining({
        params: expect.objectContaining({
          target_type: "CexToken",
          target_id: "cex_token:ZEC"
        })
      })
    );
  });

  it("seeds the audit window from the URL query", async () => {
    const getApi = vi.spyOn(client, "getApi").mockImplementation(async (path: string) => {
      if (path === "/api/target-posts") {
        return {
          ok: true,
          data: { items: [], returned_count: 0, total_count: 0, has_more: false, score_window: { window: "24h" }, query: { sort: "recent" } }
        } as any;
      }
      if (path === "/api/target-social-timeline") {
        return { ok: true, data: { stages: [], posts: [], summary: { posts: 0, authors: 0 } } } as any;
      }
      return { ok: true, data: { targets: [], attention: [], projection: {} } } as any;
    });

    renderAt("/token/CexToken/cex_token%3AZEC?window=24h");

    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith(
        "/api/token-radar",
        expect.objectContaining({
          params: expect.objectContaining({
            window: "24h"
          })
        })
      );
    });
  });
});
