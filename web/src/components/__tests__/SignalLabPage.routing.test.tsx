import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

import * as client from "../../api/client";
import { useTraderStore } from "../../store/useTraderStore";
import { SignalLabPage } from "../SignalLabPage";

beforeEach(() => {
  useTraderStore.setState({ token: "test-token", scope: "all", window: "1h" });
  vi.restoreAllMocks();
});

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/signal-lab" element={<SignalLabPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SignalLabPage routing", () => {
  it("calls list endpoint with handle and status from URL", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({
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
    } as any);
    renderAt("/signal-lab?handle=toly&status=token_watch");
    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse",
        expect.objectContaining({
          params: expect.objectContaining({ handle: "toly", status: "token_watch" }),
        }),
      );
    });
  });

  it("does not include default status param", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({
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
    } as any);
    renderAt("/signal-lab");
    await waitFor(() => expect(getApi).toHaveBeenCalled());
    const lastCall = getApi.mock.calls.at(-1)!;
    const params = (lastCall[1] as any).params;
    expect(params.status).toBeUndefined();
    expect(params.handle).toBeUndefined();
    expect(params.q).toBeUndefined();
  });

  it("uses window and scope from URL params", async () => {
    const getApi = vi.spyOn(client, "getApi").mockResolvedValue({
      ok: true,
      data: {
        query: {},
        health: {},
        summary: {},
        items: [],
        returned_count: 0,
        has_more: false,
        next_cursor: null
      }
    } as any);
    renderAt("/signal-lab?window=4h&scope=matched&q=SOL");
    await waitFor(() => {
      expect(getApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse",
        expect.objectContaining({
          params: expect.objectContaining({ window: "4h", scope: "matched", q: "SOL" })
        })
      );
    });
  });
});
