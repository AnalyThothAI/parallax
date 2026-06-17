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
    render(<MacroDataTable table={tableFixture()} caption="信用压力表" />);

    expect(screen.getByRole("region", { name: "信用压力表，可横向滚动" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "信用压力表" });
    expect(within(table).getByText("信用压力表")).toBeInTheDocument();
    expect(within(table).getByText("320.00")).toBeInTheDocument();
    expect(within(table).getByText("8.10")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("asset:spx");
    expect(table).not.toHaveTextContent("insufficient_history:60d");
    expect(table).not.toHaveTextContent("{");
  });

  it("sorts numeric columns by raw values through TanStack Table", () => {
    render(
      <MacroDataTable
        table={{
          id: "credit_stress_table",
          columns: tableFixture().columns,
          rows: [
            ...(tableFixture().rows ?? []),
            {
              row_id: "credit:missing",
              cells: {
                instrument: { display_value: "Missing spread", sort_value: "Missing spread" },
                spread: { display_value: "缺失", sort_value: null },
                yield: { display_value: "缺失", sort_value: null },
              },
            },
          ],
        }}
        caption="可排序宏观表格"
      />,
    );

    const sortButton = screen.getByRole("button", { name: "按利差排序" });
    fireEvent.click(sortButton);

    const table = screen.getByRole("table", { name: "可排序宏观表格" });
    expect(within(table).getByRole("columnheader", { name: /利差/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    let rows = within(table).getAllByRole("row");
    expect(rows[1]?.textContent).toContain("IG OAS");
    expect(rows[2]?.textContent).toContain("HY OAS");
    expect(rows[3]?.textContent).toContain("Missing spread");

    fireEvent.click(sortButton);

    expect(within(table).getByRole("columnheader", { name: /利差/ })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    rows = within(table).getAllByRole("row");
    expect(rows[1]?.textContent).toContain("HY OAS");
    expect(rows[2]?.textContent).toContain("IG OAS");
    expect(rows[3]?.textContent).toContain("Missing spread");
  });

  it("omits missing sparse cells and empty columns without placeholder text", () => {
    render(
      <MacroDataTable
        table={{
          id: "credit_stress_table",
          columns: [
            { key: "instrument", label: "指标" },
            { key: "spread", label: "利差" },
            { key: "notes", label: "备注" },
          ],
          rows: [
            {
              row_id: "credit:hy_oas",
              cells: {
                instrument: { display_value: "HY OAS", sort_value: "HY OAS" },
                spread: { display_value: null, sort_value: null },
                notes: { display_value: "", sort_value: null },
              },
            },
            {
              row_id: "credit:ig_oas",
              cells: {
                instrument: { display_value: "IG OAS", sort_value: "IG OAS" },
                spread: { display_value: "105.00", sort_value: 105 },
              },
            },
            {
              row_id: "credit:empty",
              cells: {
                instrument: { display_value: "暂无", sort_value: "empty" },
                spread: { display_value: null, sort_value: null },
              },
            },
          ],
        }}
        caption="稀疏信用表"
      />,
    );

    const table = screen.getByRole("table", { name: "稀疏信用表" });
    expect(within(table).getByText("HY OAS")).toBeInTheDocument();
    expect(within(table).getByText("IG OAS")).toBeInTheDocument();
    expect(within(table).getByText("105.00")).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: /备注/ })).not.toBeInTheDocument();
    expect(table).not.toHaveTextContent("暂无");
    expect(table).not.toHaveTextContent("credit:empty");
  });

  it("returns no table chrome when the table model has no displayable rows", () => {
    const { container } = render(
      <MacroDataTable table={{ id: "rates_snapshot", rows: [] }} caption="利率快照" />,
    );

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("status", { name: "利率快照空状态" })).not.toBeInTheDocument();
    expect(screen.queryByText("暂无表格行")).not.toBeInTheDocument();
  });

  it("renders source metadata tables without local provider inference", () => {
    render(
      <MacroSourceTable
        caption="宏观降级数据源"
        source={{
          rows: [
            {
              row_id: "source:FRED",
              source_label: "FRED",
              status: "degraded",
              status_label: "降级",
              degraded_reasons: ["provider_timeout"],
              observed_at_ms: 1_779_000_000_000,
            },
          ],
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "宏观降级数据源" });
    expect(within(table).getByText("FRED")).toBeInTheDocument();
    expect(within(table).getByText("降级")).toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "备注" })).not.toBeInTheDocument();
    expect(table).not.toHaveTextContent("provider_timeout");
  });

  it("maps known provider ids to display names in source metadata", () => {
    render(
      <MacroSourceTable
        caption="宏观数据源"
        source={{
          rows: [
            {
              row_id: "source:FRED",
              source_label: "FRED",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 3,
              score_participation: true,
            },
            {
              row_id: "source:Yahoo",
              source_label: "Yahoo",
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

  it("drops source rows without a real provider label and omits sparse fallback cells", () => {
    render(
      <MacroSourceTable
        caption="稀疏数据源"
        source={{
          rows: [
            {
              row_id: "source:FRED",
              source_label: "FRED",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 3,
            },
            {
              source: "provider_not_configured",
              status: "provider_not_configured",
              message: "provider_not_configured",
            },
          ],
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "稀疏数据源" });
    expect(within(table).getByText("FRED")).toBeInTheDocument();
    expect(within(table).getByText("2026-05-20")).toBeInTheDocument();
    expect(within(table).getByText("3")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("暂无");
    expect(table).not.toHaveTextContent("provider_not_configured");
    expect(within(table).queryByRole("columnheader", { name: "计分" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("columnheader", { name: "备注" })).not.toBeInTheDocument();
  });

  it("drops source rows without backend row ids and source labels", () => {
    const { container } = render(
      <MacroSourceTable
        caption="缺身份数据源"
        source={{
          rows: [
            {
              source_label: "FRED",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 3,
            },
            {
              row_id: "source:Yahoo",
              source: "yahoo",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 2,
            },
            {
              row_id: "source:Legacy",
              label: "Legacy Provider",
              status: "ok",
              latest_observed_at: "2026-05-20",
              concept_count: 1,
            },
          ],
        }}
      />,
    );

    expect(screen.queryByRole("table", { name: "缺身份数据源" })).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("FRED");
    expect(container).not.toHaveTextContent("Yahoo");
    expect(container).not.toHaveTextContent("Legacy Provider");
  });

  it("drops unmapped source statuses instead of manufacturing placeholder labels", () => {
    const { container } = render(
      <MacroSourceTable
        caption="异常状态数据源"
        source={{
          rows: [
            { row_id: "source:FRED", source_label: "FRED", status: "provider_not_configured" },
          ],
        }}
      />,
    );

    expect(screen.queryByRole("table", { name: "异常状态数据源" })).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("未知状态");
    expect(container).not.toHaveTextContent("provider_not_configured");
  });

  it("drops coded source degradation reasons instead of manufacturing note copy", () => {
    render(
      <MacroSourceTable
        caption="降级原因数据源"
        source={{
          rows: [
            {
              row_id: "source:FRED",
              source_label: "FRED",
              status_label: "部分可用",
              degraded_reasons: ["provider_not_configured"],
            },
          ],
        }}
      />,
    );

    const table = screen.getByRole("table", { name: "降级原因数据源" });
    expect(within(table).getByText("FRED")).toBeInTheDocument();
    expect(within(table).getByText("部分可用")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("存在降级原因");
    expect(table).not.toHaveTextContent("provider_not_configured");
    expect(within(table).queryByRole("columnheader", { name: "备注" })).not.toBeInTheDocument();
  });

  it("deletes empty source metadata state instead of inferring legacy rows", () => {
    const { container } = render(
      <MacroSourceTable
        caption="旧数据源"
        source={{ name: "fred", status: "provider_not_configured", run_id: "run-1" }}
      />,
    );

    expect(screen.queryByRole("status", { name: "旧数据源空状态" })).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent("暂无数据源元信息");
    expect(container).not.toHaveTextContent("fred");
    expect(container).not.toHaveTextContent("provider_not_configured");
    expect(container).not.toHaveTextContent("run-1");
  });
});

function tableFixture(): MacroModuleTable {
  return {
    id: "credit_stress_table",
    columns: [
      { key: "instrument", label: "指标" },
      { key: "spread", label: "利差" },
      { key: "yield", label: "收益率" },
    ],
    rows: [
      {
        row_id: "credit:hy_oas",
        cells: {
          instrument: { display_value: "HY OAS", sort_value: "HY OAS" },
          spread: { display_value: "320.00", sort_value: 320 },
          yield: { display_value: "8.10", sort_value: 8.1 },
        },
      },
      {
        row_id: "credit:ig_oas",
        cells: {
          instrument: { display_value: "IG OAS", sort_value: "IG OAS" },
          spread: { display_value: "105.00", sort_value: 105 },
          yield: { display_value: "5.40", sort_value: 5.4 },
        },
      },
    ],
  };
}
