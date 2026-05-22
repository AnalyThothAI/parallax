import { MacroDataTable } from "@features/macro/ui/tables/MacroDataTable";
import { MacroSourceTable } from "@features/macro/ui/tables/MacroSourceTable";
import type { MacroModuleTable } from "@lib/types";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("Macro table primitives", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders backend table rows with formatted numeric display", () => {
    render(<MacroDataTable table={tableFixture()} caption="CEX perp board" />);

    const table = screen.getByRole("table", { name: "CEX perp board" });
    expect(within(table).getByText("12,500,000,000")).toBeInTheDocument();
    expect(within(table).getByText("0.0001")).toBeInTheDocument();
  });

  it("sorts numeric columns by raw values through TanStack Table", () => {
    render(
      <MacroDataTable
        table={{
          table_id: "cex_perp_board",
          rows: [
            ...(tableFixture().rows ?? []),
            { symbol: "SOL", open_interest_usd: null, funding_rate: null },
          ],
        }}
        caption="Sortable macro table"
      />,
    );

    const sortButton = screen.getByRole("button", { name: "Sort by Open Interest Usd" });
    fireEvent.click(sortButton);

    const table = screen.getByRole("table", { name: "Sortable macro table" });
    expect(within(table).getByRole("columnheader", { name: /Open Interest Usd/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    let rows = within(table).getAllByRole("row");
    expect(rows[1]?.textContent).toContain("ETH");
    expect(rows[2]?.textContent).toContain("BTC");
    expect(rows[3]?.textContent).toContain("SOL");

    fireEvent.click(sortButton);

    expect(within(table).getByRole("columnheader", { name: /Open Interest Usd/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    rows = within(table).getAllByRole("row");
    expect(rows[1]?.textContent).toContain("BTC");
    expect(rows[2]?.textContent).toContain("ETH");
    expect(rows[3]?.textContent).toContain("SOL");
  });

  it("renders stable loading and empty states with accessible status labels", () => {
    const { rerender } = render(
      <MacroDataTable table={{ table_id: "rates_snapshot", rows: [] }} caption="Rates snapshot" state="loading" />,
    );

    expect(screen.getByRole("status", { name: "Rates snapshot loading state" })).toHaveTextContent(
      "table_loading",
    );

    rerender(<MacroDataTable table={{ table_id: "rates_snapshot", rows: [] }} caption="Rates snapshot" />);

    expect(screen.getByRole("status", { name: "Rates snapshot empty state" })).toHaveTextContent(
      "table_rows_missing",
    );
  });

  it("renders source metadata tables without local provider inference", () => {
    render(
      <MacroSourceTable
        caption="CEX source"
        source={{
          name: "cex_market_intel",
          status: "degraded",
          degraded_reasons: ["coinglass_partial"],
          observed_at_ms: 1_779_000_000_000,
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "CEX source" });
    expect(within(table).getByText("cex_market_intel")).toBeInTheDocument();
    expect(within(table).getByText("coinglass_partial")).toBeInTheDocument();
  });
});

function tableFixture(): MacroModuleTable {
  return {
    table_id: "cex_perp_board",
    rows: [
      { symbol: "BTC", open_interest_usd: 12_500_000_000, funding_rate: "0.0001" },
      { symbol: "ETH", open_interest_usd: 8_300_000_000, funding_rate: "-0.0002" },
    ],
  };
}
