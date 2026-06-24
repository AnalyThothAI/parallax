import {
  buildMacroTableModel,
  compareMacroTableSortValues,
  formatMacroTableValue,
  sortMacroTableRows,
} from "@features/macro/model/macroTableColumns";
import type { MacroModuleTable } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroTableColumns", () => {
  it("keeps numeric raw values for sorting while displaying formatted values", () => {
    const table: MacroModuleTable = {
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

    const model = buildMacroTableModel(table);

    expect(model.columns).toEqual([
      { id: "instrument", label: "指标" },
      { id: "spread", label: "利差" },
      { id: "yield", label: "收益率" },
    ]);
    expect(model.rows[0]?.cells.spread).toMatchObject({
      rawValue: 320,
      sortValue: 320,
      displayValue: "320.00",
      isNumeric: true,
    });
    expect(model.rows[1]?.cells.yield).toMatchObject({
      rawValue: 5.4,
      sortValue: 5.4,
      displayValue: "5.40",
      isNumeric: true,
    });
  });

  it("sorts by backend sort values instead of display labels", () => {
    const model = buildMacroTableModel({
      id: "rates_snapshot",
      columns: [
        { key: "indicator", label: "指标" },
        { key: "latest", label: "最新值" },
      ],
      rows: [
        {
          row_id: "rates:dgs10",
          cells: {
            indicator: { display_value: "10年期美债收益率", sort_value: "10Y" },
            latest: { display_value: "10.50", sort_value: 10.5 },
          },
        },
        {
          row_id: "rates:dgs2",
          cells: {
            indicator: { display_value: "2年期美债收益率", sort_value: "2Y" },
            latest: { display_value: "2.00", sort_value: 2 },
          },
        },
      ],
    });

    const sorted = sortMacroTableRows(model.rows, "latest", "asc");

    expect(sorted.map((row) => row.cells.indicator?.displayValue)).toEqual([
      "2年期美债收益率",
      "10年期美债收益率",
    ]);
    expect(sorted.map((row) => row.cells.indicator?.displayValue)).not.toContain("rates:dgs10");
  });

  it("keeps missing values last for both ascending and descending helper sorts", () => {
    const model = buildMacroTableModel({
      id: "rates_snapshot",
      columns: [
        { key: "indicator", label: "指标" },
        { key: "latest", label: "最新值" },
      ],
      rows: [
        {
          row_id: "rates:dgs10",
          cells: {
            indicator: { display_value: "10年期美债收益率", sort_value: "10Y" },
            latest: { display_value: "10.50", sort_value: 10.5 },
          },
        },
        {
          row_id: "rates:dgs2",
          cells: {
            indicator: { display_value: "2年期美债收益率", sort_value: "2Y" },
            latest: { display_value: "缺失", sort_value: null },
          },
        },
        {
          row_id: "rates:dgs5",
          cells: {
            indicator: { display_value: "5年期美债收益率", sort_value: "5Y" },
            latest: { display_value: "5.00", sort_value: 5 },
          },
        },
      ],
    });

    expect(
      sortMacroTableRows(model.rows, "latest", "asc").map(
        (row) => row.cells.indicator?.displayValue,
      ),
    ).toEqual(["5年期美债收益率", "10年期美债收益率", "2年期美债收益率"]);
    expect(
      sortMacroTableRows(model.rows, "latest", "desc").map(
        (row) => row.cells.indicator?.displayValue,
      ),
    ).toEqual(["10年期美债收益率", "5年期美债收益率", "2年期美债收益率"]);
  });

  it("does not derive user-facing columns or JSON display from arbitrary row objects", () => {
    const model = buildMacroTableModel({
      id: "source_metadata",
      rows: [
        {
          concept_key: "asset:spx",
          latest: { raw: true },
          reason: "insufficient_history:60d",
        },
      ],
    });

    expect(model.columns).toEqual([]);
    expect(model.rows).toEqual([]);
  });

  it("drops sparse table placeholders, empty rows, and empty columns", () => {
    const model = buildMacroTableModel({
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
            instrument: { display_value: "", sort_value: "empty" },
            spread: { display_value: null, sort_value: null },
          },
        },
      ],
    });

    expect(model.columns.map((column) => column.id)).toEqual(["instrument", "spread"]);
    expect(model.rows.map((row) => row.id)).toEqual(["credit:hy_oas", "credit:ig_oas"]);
    expect(model.rows[0]?.cells.spread).toBeUndefined();
    expect(JSON.stringify(model)).not.toContain("暂无");
    expect(JSON.stringify(model)).not.toContain("credit:empty");
  });

  it("drops rows without backend row_id instead of deriving synthetic row ids", () => {
    const model = buildMacroTableModel({
      id: "asset_snapshot",
      columns: [{ key: "instrument", label: "指标" }],
      rows: [
        {
          concept_key: "asset:spx",
          cells: {
            instrument: { display_value: "S&P 500", sort_value: "SPX" },
          },
        },
        {
          label: "TLT",
          cells: {
            instrument: { display_value: "TLT", sort_value: "TLT" },
          },
        },
        {
          id: "legacy-id",
          cells: {
            instrument: { display_value: "DXY", sort_value: "DXY" },
          },
        },
      ],
    });

    expect(model.rows).toEqual([]);
    expect(JSON.stringify(model)).not.toContain("asset:spx");
    expect(JSON.stringify(model)).not.toContain("row:0");
    expect(JSON.stringify(model)).not.toContain("legacy-id");
  });

  it("drops table models with missing table ids instead of assigning unknown ids", () => {
    const model = buildMacroTableModel({
      id: "",
      columns: [{ key: "indicator", label: "指标" }],
      rows: [
        {
          row_id: "asset:spx",
          cells: {
            indicator: { display_value: "S&P 500", sort_value: "S&P 500" },
          },
        },
      ],
    });

    expect(model).toEqual({
      columns: [],
      rows: [],
      tableId: "",
    });
    expect(JSON.stringify(model)).not.toContain("unknown_table");
  });

  it("does not expose table object labels or titles without display values", () => {
    expect(formatMacroTableValue({ label: "legacy object label" })).toBeNull();
    expect(formatMacroTableValue({ title: "legacy object title" })).toBeNull();

    const model = buildMacroTableModel({
      id: "legacy_object_table",
      columns: [
        { key: "indicator", label: "指标" },
        { key: "value", label: "值" },
      ],
      rows: [
        {
          row_id: "row:legacy",
          cells: {
            indicator: { label: "legacy object label" },
            value: { title: "legacy object title" },
          },
        },
        {
          row_id: "row:display",
          cells: {
            indicator: { display_value: "显式指标", sort_value: "显式指标" },
            value: { display_value: "显式值", sort_value: "显式值" },
          },
        },
      ],
    });

    expect(model.rows.map((row) => row.id)).toEqual(["row:display"]);
    expect(JSON.stringify(model)).not.toContain("legacy object label");
    expect(JSON.stringify(model)).not.toContain("legacy object title");
  });

  it("formats arrays and empty values without changing raw sort semantics", () => {
    expect(
      formatMacroTableValue([
        { code: "insufficient_history:60d", label: "历史样本不足：无法计算 60 日变化" },
      ]),
    ).toBeNull();
    expect(formatMacroTableValue({ raw: true })).toBeNull();
    expect(formatMacroTableValue({ display_value: "来源可用", sort_value: "ok" })).toBe("来源可用");
    expect(formatMacroTableValue(null)).toBeNull();
    expect(formatMacroTableValue("unknown")).toBe("unknown");
    expect(compareMacroTableSortValues(2, 10)).toBeLessThan(0);
    expect(compareMacroTableSortValues("asset:qqq", "asset:spy")).toBeLessThan(0);
  });

  it("does not infer raw or sort values from display-cell text", () => {
    const model = buildMacroTableModel({
      id: "source_status_table",
      columns: [
        { key: "source", label: "来源" },
        { key: "latest", label: "最新值" },
      ],
      rows: [
        {
          row_id: "source:FRED",
          cells: {
            source: { display_value: "FRED" },
            latest: { display_value: "320.00" },
          },
        },
      ],
    });

    expect(model.rows[0]?.cells.source).toMatchObject({
      displayValue: "FRED",
      rawValue: null,
      sortValue: null,
      isNumeric: false,
    });
    expect(model.rows[0]?.cells.latest).toMatchObject({
      displayValue: "320.00",
      rawValue: null,
      sortValue: null,
      isNumeric: false,
    });
  });

  it("does not translate table scalar status codes into synthetic labels", () => {
    expect(formatMacroTableValue("ok")).toBe("ok");
    expect(formatMacroTableValue("partial")).toBe("partial");
    expect(formatMacroTableValue("unavailable")).toBe("unavailable");

    const model = buildMacroTableModel({
      id: "source_status_table",
      columns: [{ key: "status", label: "状态" }],
      rows: [
        {
          row_id: "source:FRED",
          cells: {
            status: { display_value: "partial", sort_value: "partial" },
          },
        },
      ],
    });

    expect(model.rows[0]?.cells.status?.displayValue).toBe("partial");
  });
});
