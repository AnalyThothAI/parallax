import { setAuthToken } from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { createApiMock, ok, resetApiMock } from "../../../../test/msw/fixtures";
import { apiHandlers } from "../../../../test/msw/handlers";
import { server } from "../../../../test/msw/server";
import { SignalLabPage } from "../SignalLabPage";

const apiMock = createApiMock();

beforeEach(() => {
  setAuthToken("test-token");
  resetApiMock(apiMock);
  apiMock.readApiImpl = async () =>
    ok({
      query: {},
      health: {},
      summary: {},
      items: [],
      returned_count: 0,
      has_more: false,
      next_cursor: null,
    });
  server.use(...apiHandlers(apiMock));
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
    renderAt("/signal-lab?handle=toly&status=token_watch");
    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse",
        expect.objectContaining({
          params: expect.objectContaining({ handle: "toly", status: "token_watch" }),
        }),
      );
    });
  });

  it("does not include default status param", async () => {
    renderAt("/signal-lab");
    await waitFor(() => expect(apiMock.readApi).toHaveBeenCalled());
    const lastCall = apiMock.readApi.mock.calls.at(-1)!;
    const params = (lastCall[1] as any).params;
    expect(params.status).toBeUndefined();
    expect(params.handle).toBeUndefined();
    expect(params.q).toBeUndefined();
  });

  it("uses window and scope from URL params", async () => {
    renderAt("/signal-lab?window=4h&scope=matched&q=SOL");
    await waitFor(() => {
      expect(apiMock.readApi).toHaveBeenCalledWith(
        "/api/signal-lab/pulse",
        expect.objectContaining({
          params: expect.objectContaining({ window: "4h", scope: "matched", q: "SOL" }),
        }),
      );
    });
  });
});
