import { NewsPage } from "@features/news";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@lib/api/client", () => ({
  fetchNewsRows: async () => ({
    items: [
      {
        row_id: "row-1",
        news_item_id: "news-1",
        lifecycle_status: "attention",
        headline: "Coinbase lists NEWX",
        summary: "Trading starts today",
        source_domain: "example.test",
        token_lanes: [{ lane: "attention", resolution_status: "unknown_attention", symbol: "NEWX" }],
        fact_lanes: [{ event_type: "listing", status: "attention" }],
      },
    ],
    next_cursor: null,
  }),
}));

describe("NewsPage", () => {
  it("renders news lifecycle and attention lanes", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <NewsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Coinbase lists NEWX")).toBeInTheDocument();
    expect(screen.getByText("Attention")).toBeInTheDocument();
    expect(screen.getByText("NEWX · attention")).toBeInTheDocument();
    expect(screen.getByText("listing · attention")).toBeInTheDocument();
  });
});
