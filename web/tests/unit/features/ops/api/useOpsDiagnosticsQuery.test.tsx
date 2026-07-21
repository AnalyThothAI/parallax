import { useOpsDiagnosticsQuery, useOpsQueueQuery } from "@features/ops/api/useOpsDiagnosticsQuery";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { opsDiagnosticsFixture, opsQueueFixture } from "@tests/fixtures/opsFixture";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("ops query current contracts", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("surfaces malformed diagnostics as a query error", async () => {
    const payload = { ...opsDiagnosticsFixture() } as Record<string, unknown>;
    delete payload.agent_execution;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true, data: payload }));

    const { result } = renderHook(() => useOpsDiagnosticsQuery({ token: "secret" }), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toHaveProperty("message", "ops_current_contract:diagnostics");
  });

  it("surfaces malformed queue detail as a query error", async () => {
    const payload = { ...opsQueueFixture() } as Record<string, unknown>;
    delete payload.summary;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true, data: payload }));

    const { result } = renderHook(
      () =>
        useOpsQueueQuery({
          enabled: true,
          queueName: "notification_deliveries",
          token: "secret",
        }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toHaveProperty("message", "ops_current_contract:queue");
  });
});

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
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
