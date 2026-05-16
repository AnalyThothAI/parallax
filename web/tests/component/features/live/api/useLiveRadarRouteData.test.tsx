import { useLiveRadarRouteData } from "@features/live";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("useLiveRadarRouteData", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps projection-pending responses in the loading state instead of reporting empty rows", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        ok: true,
        data: {
          window: "1h",
          scope: "all",
          targets: [],
          attention: [],
          projection: {
            status: "pending",
            version: "token-radar-route-fixture",
            source: "route_test",
            reason: "projection_window_running",
            row_count: 0,
            source_rows: 3,
          },
        },
      }),
    );

    const { result } = renderHook(
      () => useLiveRadarRouteData({ scope: "all", token: "secret", window: "1h" }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.projectionStatus).toBe("pending"), {
      timeout: 1_000,
    });
    expect(result.current.isAssetFlowLoading).toBe(true);
    expect(result.current.tokenItems).toEqual([]);
  });
});

function wrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    status: 200,
  });
}
