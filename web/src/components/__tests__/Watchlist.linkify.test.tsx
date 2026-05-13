import * as client from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { App } from "../../App";

vi.mock("../../api/useIntelSocket", () => ({
  useIntelSocket: () => ({
    status: "connected",
    events: [],
    notifications: [],
    lastMessageAt: null,
  }),
}));

beforeEach(() => {
  client.setAuthToken("test-token");
  vi.restoreAllMocks();
});

describe("watchlist sidebar", () => {
  it("renders each handle as a Link to /signal-lab?handle=...", async () => {
    vi.spyOn(client, "getBootstrap").mockResolvedValue({
      ok: true,
      data: { ws_token: "test-token", handles: ["toly"], replay_limit: 25 },
    } as any);
    vi.spyOn(client, "getApi").mockImplementation(async (path: string) => {
      if (path === "/api/status") {
        return {
          ok: true,
          data: { ok: true, handles: ["toly"], collector: {}, notifications: { summary: {} } },
        } as any;
      }
      if (path === "/api/recent") {
        return { ok: true, data: { items: [] } } as any;
      }
      if (path === "/api/token-radar") {
        return { ok: true, data: { targets: [], attention: [], projection: {} } } as any;
      }
      if (path === "/api/signal-lab/pulse") {
        return {
          ok: true,
          data: {
            query: {},
            health: {},
            summary: {},
            items: [],
            returned_count: 0,
            has_more: false,
            next_cursor: null,
          },
        } as any;
      }
      if (path === "/api/notification-summary") {
        return { ok: true, data: {} } as any;
      }
      if (path === "/api/notifications") {
        return { ok: true, data: { items: [], summary: {} } } as any;
      }
      return { ok: true, data: {} } as any;
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const link = await waitFor(() => screen.getByRole("link", { name: /toly/i }));
    expect(link.getAttribute("href")).toBe("/signal-lab?handle=toly");
    expect(link).toHaveClass("watchlist-row");
  });
});
