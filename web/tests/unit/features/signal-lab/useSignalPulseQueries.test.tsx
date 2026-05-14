import { useSourceEvents } from "@features/signal-lab/api/useSignalPulseQueries";
import * as apiClient from "@lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => vi.restoreAllMocks());

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useSourceEvents", () => {
  it("calls /api/social-events/by-ids with ids", async () => {
    const spy = vi.spyOn(apiClient, "getApi").mockResolvedValue({
      ok: true,
      data: { events: [], not_found: [] },
    } as never);

    const { result } = renderHook(
      () => useSourceEvents({ token: "secret", ids: ["b", "a"] }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      "/api/social-events/by-ids",
      expect.objectContaining({ token: "secret", params: { ids: "b,a" } }),
    );
  });

  it("is disabled with empty ids", () => {
    const spy = vi.spyOn(apiClient, "getApi");

    renderHook(() => useSourceEvents({ token: "secret", ids: [] }), { wrapper: wrapper() });

    expect(spy).not.toHaveBeenCalled();
  });
});
