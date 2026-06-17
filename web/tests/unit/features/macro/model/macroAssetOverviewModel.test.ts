import {
  buildAssetMarketGroups,
  normalizeDailyBrief,
} from "@features/macro/model/macroAssetOverviewModel";
import type { MacroModuleTable } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroAssetOverviewModel", () => {
  it("does not preserve pending placeholders for asset rows without date or source evidence", () => {
    const table: MacroModuleTable = {
      id: "asset_group_snapshot",
      columns: [
        { key: "symbol", label: "代码" },
        { key: "indicator", label: "名称" },
        { key: "latest", label: "最新" },
        { key: "delta_20d", label: "20日变化" },
        { key: "observed_at", label: "日期" },
        { key: "source", label: "来源" },
      ],
      rows: [
        {
          row_id: "asset:spx",
          cells: {
            symbol: { display_value: "SPX", sort_value: "SPX" },
            indicator: { display_value: "标普500", sort_value: "标普500" },
            latest: { display_value: "5,312.40", sort_value: 5312.4 },
            delta_20d: { display_value: "+0.30%", sort_value: 0.3 },
          },
        },
      ],
    };

    const groups = buildAssetMarketGroups(table);

    expect(groups[0]?.rows[0]).toMatchObject({
      asOf: null,
      quality: null,
    });
    expect(JSON.stringify(groups)).not.toContain("待确认");
  });

  it("does not backfill asset row dates from module snapshot dates", () => {
    const table: MacroModuleTable = {
      id: "asset_group_snapshot",
      columns: [
        { key: "symbol", label: "代码" },
        { key: "indicator", label: "名称" },
        { key: "latest", label: "最新" },
      ],
      rows: [
        {
          row_id: "asset:spx",
          cells: {
            symbol: { display_value: "SPX", sort_value: "SPX" },
            indicator: { display_value: "标普500", sort_value: "标普500" },
            latest: { display_value: "5,312.40", sort_value: 5312.4 },
          },
        },
      ],
    };

    const groups = buildAssetMarketGroups(table);

    expect(groups[0]?.rows[0]?.asOf).toBeNull();
    expect(JSON.stringify(groups)).not.toContain("2026-05-20");
  });

  it("drops asset market rows without a name or latest value and keeps optional fields absent", () => {
    const table: MacroModuleTable = {
      id: "asset_group_snapshot",
      columns: [
        { key: "symbol", label: "代码" },
        { key: "indicator", label: "名称" },
        { key: "latest", label: "最新" },
        { key: "delta_20d", label: "20日变化" },
      ],
      rows: [
        {
          row_id: "asset:spx",
          cells: {
            symbol: { display_value: "SPX", sort_value: "SPX" },
            indicator: { display_value: "标普500", sort_value: "SPX" },
            latest: { display_value: "5,312.40", sort_value: 5312.4 },
          },
        },
        {
          row_id: "asset:dji",
          cells: {
            indicator: { display_value: "道琼斯", sort_value: "DJI" },
            latest: { display_value: "38,100.00", sort_value: 38100 },
          },
        },
        {
          row_id: "asset:qqq",
          cells: {
            indicator: { display_value: "纳斯达克100", sort_value: "QQQ" },
            latest: { display_value: "", sort_value: null },
          },
        },
        {
          row_id: "asset:iwm",
          cells: {
            indicator: { display_value: "", sort_value: null },
            latest: { display_value: "201.20", sort_value: 201.2 },
          },
        },
        {
          row_id: "fx:",
          cells: {
            indicator: { display_value: "美元指数", sort_value: "DXY" },
            latest: { display_value: "99.97", sort_value: 99.97 },
          },
        },
      ],
    };

    const groups = buildAssetMarketGroups(table);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.rows).toHaveLength(1);
    expect(groups[0]?.rows[0]).toMatchObject({
      delta: null,
      latest: "5,312.40",
      name: "标普500",
      symbol: "SPX",
    });
    expect(JSON.stringify(groups)).not.toContain("暂无");
    expect(JSON.stringify(groups)).not.toContain("DJI");
    expect(JSON.stringify(groups)).not.toContain("QQQ");
    expect(JSON.stringify(groups)).not.toContain("IWM");
  });

  it("does not manufacture daily brief headline, status, stance, or quality status", () => {
    expect(normalizeDailyBrief({ headline: "Risk on", blocks: [] })).toBeNull();
    expect(normalizeDailyBrief({ status: "supported", blocks: [] })).toBeNull();

    const brief = normalizeDailyBrief({
      blocks: [
        {
          body: "真实信号",
          id: "growth",
          title: "增长",
        },
      ],
      data_quality: {
        gap_count: 2,
        latest_coverage_ratio: 0.7,
      },
      headline: "Risk on",
      status: "supported",
    });

    expect(brief).toMatchObject({
      blocks: [],
      dataQuality: undefined,
      headline: "Risk on",
      status: "supported",
    });
    expect(JSON.stringify(brief)).not.toContain("unknown");
    expect(JSON.stringify(brief)).not.toContain("neutral");
    expect(JSON.stringify(brief)).not.toContain("今日判断暂不可用");
  });
});
