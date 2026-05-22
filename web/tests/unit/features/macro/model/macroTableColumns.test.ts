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
      table_id: "cex_perp_board",
      rows: [
        { symbol: "BTC", open_interest_usd: 12_500_000_000, funding_rate: "0.0001" },
        { symbol: "ETH", open_interest_usd: 8_300_000_000, funding_rate: "-0.0002" },
      ],
    };

    const model = buildMacroTableModel(table);

    expect(model.columns.map((column) => column.id)).toEqual([
      "symbol",
      "open_interest_usd",
      "funding_rate",
    ]);
    expect(model.rows[0]?.cells.open_interest_usd).toMatchObject({
      rawValue: 12_500_000_000,
      sortValue: 12_500_000_000,
      displayValue: "12,500,000,000",
      isNumeric: true,
    });
    expect(model.rows[1]?.cells.funding_rate).toMatchObject({
      rawValue: -0.0002,
      sortValue: -0.0002,
      displayValue: "-0.0002",
      isNumeric: true,
    });
  });

  it("sorts numeric strings by raw number instead of lexical order", () => {
    const model = buildMacroTableModel({
      table_id: "rates_snapshot",
      rows: [
        { concept_key: "rates:dgs10", latest: "10.5", unit: "percent" },
        { concept_key: "rates:dgs2", latest: "2", unit: "percent" },
      ],
    });

    const sorted = sortMacroTableRows(model.rows, "latest", "asc");

    expect(sorted.map((row) => row.cells.concept_key?.displayValue)).toEqual(["rates:dgs2", "rates:dgs10"]);
  });

  it("keeps missing values last for both ascending and descending helper sorts", () => {
    const model = buildMacroTableModel({
      table_id: "rates_snapshot",
      rows: [
        { concept_key: "rates:dgs10", latest: 10.5 },
        { concept_key: "rates:dgs2", latest: null },
        { concept_key: "rates:dgs5", latest: 5 },
      ],
    });

    expect(sortMacroTableRows(model.rows, "latest", "asc").map((row) => row.cells.concept_key?.displayValue)).toEqual([
      "rates:dgs5",
      "rates:dgs10",
      "rates:dgs2",
    ]);
    expect(sortMacroTableRows(model.rows, "latest", "desc").map((row) => row.cells.concept_key?.displayValue)).toEqual([
      "rates:dgs10",
      "rates:dgs5",
      "rates:dgs2",
    ]);
  });

  it("formats arrays and empty values without changing raw sort semantics", () => {
    expect(formatMacroTableValue(["missing:rates:dgs5", "move_index_missing"])).toBe(
      "missing:rates:dgs5, move_index_missing",
    );
    expect(formatMacroTableValue(null)).toBe("n/a");
    expect(compareMacroTableSortValues(2, 10)).toBeLessThan(0);
    expect(compareMacroTableSortValues("asset:qqq", "asset:spy")).toBeLessThan(0);
  });
});
