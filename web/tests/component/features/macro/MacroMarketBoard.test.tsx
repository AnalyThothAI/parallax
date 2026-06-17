import { MacroMarketBoard } from "@features/macro/ui/pages/MacroMarketBoard";
import type { MacroModuleTable } from "@lib/types";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

describe("MacroMarketBoard", () => {
  afterEach(() => {
    cleanup();
  });

  it("omits table source notes whose formatted copy is empty", () => {
    const { container } = render(
      <MacroMarketBoard
        chart={{ id: "credit_chart", series: [] }}
        moduleId="credit/stress"
        supportingTable={{
          id: "credit_table",
          title: "信用表",
          columns: [
            { key: "instrument", label: "指标" },
            { key: "spread", label: "利差" },
          ],
          rows: [
            {
              row_id: "credit:hy_oas",
              cells: {
                instrument: { display_value: "HY OAS", sort_value: "HY OAS" },
                spread: { display_value: "320.00", sort_value: 320 },
              },
            },
          ],
          source: { notes: { raw: true } },
        }}
        title="主市场证据"
      />,
    );

    expect(screen.getByRole("table", { name: "信用表" })).toBeInTheDocument();
    expect(screen.queryByText("暂无可绘制序列")).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("unknown");
    expect(container.querySelector(".macro-table-source-note")).not.toBeInTheDocument();
  });

  it("omits chart chrome when chart series are not renderable after model filtering", () => {
    render(
      <MacroMarketBoard
        chart={{ id: "asset_proxy_performance", series: [{ concept_key: "asset:spx" }] }}
        moduleId="assets/equities"
        supportingTable={{
          id: "asset_table",
          title: "资产表",
          columns: [
            { key: "instrument", label: "资产" },
            { key: "latest", label: "最新值" },
          ],
          rows: [
            {
              row_id: "asset:spx",
              cells: {
                instrument: { display_value: "S&P 500", sort_value: "S&P 500" },
                latest: { display_value: "6500", sort_value: 6500 },
              },
            },
          ],
        }}
        title="主市场证据"
      />,
    );

    expect(screen.getByRole("table", { name: "资产表" })).toBeInTheDocument();
    expect(screen.queryByText("暂无可绘制序列")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("资产 代理 表现")).not.toBeInTheDocument();
  });

  it("drops supporting tables without backend ids and titles", () => {
    render(
      <MacroMarketBoard
        chart={{ id: "credit_chart", series: [] }}
        moduleId="credit/stress"
        supportingTable={
          {
            title: "缺少 ID 的表",
            columns: [{ key: "instrument", label: "指标" }],
            rows: [
              {
                row_id: "credit:hy_oas",
                cells: {
                  instrument: { display_value: "HY OAS", sort_value: "HY OAS" },
                },
              },
            ],
          } as unknown as MacroModuleTable
        }
        supportingTables={[
          {
            id: "missing_title",
            columns: [{ key: "instrument", label: "指标" }],
            rows: [
              {
                row_id: "credit:ig_oas",
                cells: {
                  instrument: { display_value: "IG OAS", sort_value: "IG OAS" },
                },
              },
            ],
          },
        ]}
        title="主市场证据"
      />,
    );

    expect(screen.queryByRole("region", { name: "主市场证据" })).not.toBeInTheDocument();
    expect(screen.queryByText("HY OAS")).not.toBeInTheDocument();
    expect(screen.queryByText("IG OAS")).not.toBeInTheDocument();
  });
});
