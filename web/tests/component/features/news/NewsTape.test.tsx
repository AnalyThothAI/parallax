import { NewsTape } from "@features/news/ui/NewsTape";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { newsRowFixture } from "@tests/fixtures/newsFixture";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("NewsTape", () => {
  afterEach(cleanup);

  it("renders compact rows from lifecycle, source, story, rating, and token facts", () => {
    render(<NewsTape rows={[newsRowFixture()]} onOpen={vi.fn()} />);

    expect(screen.getByText("processed")).toBeInTheDocument();
    expect(screen.getByText("market_update")).toBeInTheDocument();
    expect(screen.getByText("OPENNEWS")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("ETH")).toBeInTheDocument();
    expect(screen.getByText("2 story members")).toBeInTheDocument();
    expect(screen.getAllByText("resolved")).toHaveLength(2);
  });

  it("opens one news item as one row even with multiple token chips", () => {
    const onOpen = vi.fn();
    render(<NewsTape rows={[newsRowFixture()]} onOpen={onOpen} />);

    fireEvent.click(screen.getByRole("button", { name: "Open news item BTC ETF flows expand" }));
    expect(onOpen).toHaveBeenCalledWith("news-1");

    fireEvent.click(screen.getByRole("button", { name: "Open BTC ETF flows expand" }));
    expect(onOpen).toHaveBeenCalledTimes(2);
  });
});
