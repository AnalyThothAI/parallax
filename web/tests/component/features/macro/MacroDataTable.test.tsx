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
    render(<MacroDataTable table={tableFixture()} caption="CEX 永续看板" />);

    expect(screen.getByRole("region", { name: "CEX 永续看板，可横向滚动" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "CEX 永续看板" });
    expect(within(table).getByText("CEX 永续看板")).toBeInTheDocument();
    expect(within(table).getByText("12.50B")).toBeInTheDocument();
    expect(within(table).getByText("0.0100%")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("asset:spx");
    expect(table).not.toHaveTextContent("insufficient_history:60d");
    expect(table).not.toHaveTextContent("{");
  });

  it("sorts numeric columns by raw values through TanStack Table", () => {
    render(
      <MacroDataTable
        table={{
          id: "cex_perp_board",
          columns: tableFixture().columns,
          rows: [
            ...(tableFixture().rows ?? []),
            {
              row_id: "SOLUSDT",
              cells: {
                symbol: { display_value: "SOL", sort_value: "SOL" },
                open_interest: { display_value: "缺失", sort_value: null },
                funding: { display_value: "缺失", sort_value: null },
              },
            },
          ],
        }}
        caption="可排序宏观表格"
      />,
    );

    const sortButton = screen.getByRole("button", { name: "按未平仓排序" });
    fireEvent.click(sortButton);

    const table = screen.getByRole("table", { name: "可排序宏观表格" });
    expect(within(table).getByRole("columnheader", { name: /未平仓/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    let rows = within(table).getAllByRole("row");
    expect(rows[1]?.textContent).toContain("ETH");
    expect(rows[2]?.textContent).toContain("BTC");
    expect(rows[3]?.textContent).toContain("SOL");

    fireEvent.click(sortButton);

    expect(within(table).getByRole("columnheader", { name: /未平仓/ })).toHaveAttribute(
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
      <MacroDataTable
        table={{ id: "rates_snapshot", rows: [] }}
        caption="利率快照"
        state="loading"
      />,
    );

    expect(screen.getByRole("status", { name: "利率快照加载状态" })).toHaveTextContent(
      "表格加载中",
    );

    rerender(
      <MacroDataTable table={{ id: "rates_snapshot", rows: [] }} caption="利率快照" />,
    );

    expect(screen.getByRole("status", { name: "利率快照空状态" })).toHaveTextContent("暂无表格行");
  });

  it("renders source metadata tables without local provider inference", () => {
    render(
      <MacroSourceTable
        caption="CEX 数据源"
        source={{
          rows: [
            {
              name: "cex_market_intel",
              status: "degraded",
              status_label: "降级",
              degraded_reasons: ["coinglass_partial"],
              observed_at_ms: 1_779_000_000_000,
            },
          ],
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "CEX 数据源" });
    expect(within(table).getByText("CEX OI Radar")).toBeInTheDocument();
    expect(within(table).getByText("降级")).toBeInTheDocument();
    expect(within(table).getByText("存在降级原因")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("cex_market_intel");
    expect(table).not.toHaveTextContent("coinglass_partial");
  });

  it("maps known provider ids to display names in source metadata", () => {
    render(
      <MacroSourceTable
        caption="宏观数据源"
        source={{
          rows: [
            {
              source: "fred",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 3,
              score_participation: true,
            },
            {
              source: "yahoo",
              status: "partial",
              latest_observed_at: "2026-05-20",
              concept_count: 2,
              score_participation: false,
            },
          ],
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "宏观数据源" });
    expect(within(table).getByText("FRED")).toBeInTheDocument();
    expect(within(table).getByText("Yahoo")).toBeInTheDocument();
    expect(within(table).getByText("参与计分")).toBeInTheDocument();
    expect(within(table).getByText("计分排除")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("fred");
    expect(table).not.toHaveTextContent("yahoo");
  });

  it("does not expose unknown raw source statuses", () => {
    render(
      <MacroSourceTable
        caption="未知状态数据源"
        source={{ rows: [{ source: "fred", status: "provider_not_configured" }] }}
      />,
    );

    const table = screen.getByRole("table", { name: "未知状态数据源" });
    expect(within(table).getByText("未知状态")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("provider_not_configured");
  });

  it("does not infer rows from a legacy source metadata object", () => {
    render(
      <MacroSourceTable
        caption="旧数据源"
        source={{ name: "fred", status: "provider_not_configured", run_id: "run-1" }}
      />,
    );

    const state = screen.getByRole("status", { name: "旧数据源空状态" });
    expect(state).toHaveTextContent("暂无数据源元信息");
    expect(state).not.toHaveTextContent("fred");
    expect(state).not.toHaveTextContent("provider_not_configured");
    expect(state).not.toHaveTextContent("run-1");
  });
});

function tableFixture(): MacroModuleTable {
  return {
    id: "cex_perp_board",
    columns: [
      { key: "symbol", label: "合约" },
      { key: "open_interest", label: "未平仓" },
      { key: "funding", label: "资金费率" },
    ],
    rows: [
      {
        row_id: "BTCUSDT",
        cells: {
          symbol: { display_value: "BTC", sort_value: "BTC" },
          open_interest: { display_value: "12.50B", sort_value: 12_500_000_000 },
          funding: { display_value: "0.0100%", sort_value: 0.0001 },
        },
      },
      {
        row_id: "ETHUSDT",
        cells: {
          symbol: { display_value: "ETH", sort_value: "ETH" },
          open_interest: { display_value: "8.30B", sort_value: 8_300_000_000 },
          funding: { display_value: "-0.0200%", sort_value: -0.0002 },
        },
      },
    ],
  };
}
