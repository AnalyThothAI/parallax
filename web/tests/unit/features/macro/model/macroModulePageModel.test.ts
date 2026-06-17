import {
  chartCaption,
  chartIdentifier,
  tableCaption,
  tableIdentifier,
} from "@features/macro/model/macroModulePageModel";
import type { MacroModuleChart, MacroModuleTable } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroModulePageModel", () => {
  it("does not manufacture unknown chart or table identifiers from invalid payloads", () => {
    const invalidChart = { id: "", series: [] } as MacroModuleChart;
    const invalidTable = { id: "", rows: [] } as MacroModuleTable;

    expect(chartIdentifier(invalidChart)).toBeNull();
    expect(chartCaption(invalidChart)).toBeNull();
    expect(tableIdentifier(invalidTable)).toBeNull();
    expect(tableCaption(invalidTable)).toBeNull();
  });

  it("requires backend titles for chart and table captions", () => {
    expect(chartCaption({ id: "yield_curve", series: [] })).toBeNull();
    expect(tableCaption({ id: "yield_curve_snapshot", rows: [] })).toBeNull();
    expect(chartCaption({ id: "yield_curve", title: "收益率曲线", series: [] })).toBe("收益率曲线");
    expect(tableCaption({ id: "yield_curve_snapshot", title: "收益率曲线快照", rows: [] })).toBe(
      "收益率曲线快照",
    );
  });
});
