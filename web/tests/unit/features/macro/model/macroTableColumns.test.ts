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

    const model = buildMacroTableModel(table);

    expect(model.columns).toEqual([
      { id: "symbol", label: "合约" },
      { id: "open_interest", label: "未平仓" },
      { id: "funding", label: "资金费率" },
    ]);
    expect(model.rows[0]?.cells.open_interest).toMatchObject({
      rawValue: 12_500_000_000,
      sortValue: 12_500_000_000,
      displayValue: "12.50B",
      isNumeric: true,
    });
    expect(model.rows[1]?.cells.funding).toMatchObject({
      rawValue: -0.0002,
      sortValue: -0.0002,
      displayValue: "-0.0200%",
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
    expect(model.rows[0]?.cells).toEqual({});
  });

  it("formats arrays and empty values without changing raw sort semantics", () => {
    expect(
      formatMacroTableValue([
        { code: "insufficient_history:60d", label: "历史样本不足：无法计算 60 日变化" },
      ]),
    ).toBe("历史样本不足：无法计算 60 日变化");
    expect(formatMacroTableValue({ raw: true })).toBe("暂无");
    expect(formatMacroTableValue({ display_value: "来源可用", sort_value: "ok" })).toBe("来源可用");
    expect(formatMacroTableValue(null)).toBe("暂无");
    expect(compareMacroTableSortValues(2, 10)).toBeLessThan(0);
    expect(compareMacroTableSortValues("asset:qqq", "asset:spy")).toBeLessThan(0);
  });
});
