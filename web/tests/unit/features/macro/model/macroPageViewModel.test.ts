import {
  formatMacroScalar,
  gapLabel,
  macroAsOfLabel,
  macroFreshnessAlert,
  macroFieldLabel,
  macroStatusLabel,
} from "@features/macro/model/macroPageViewModel";
import type { MacroModuleView } from "@lib/types";
import { describe, expect, it } from "vitest";

import { macroModuleFixture } from "../../../../fixtures/macroFixture";

describe("macroPageViewModel", () => {
  it("uses display-ready v3 labels and never surfaces raw gap strings", () => {
    expect(gapLabel({ code: "insufficient_history:60d", label: "历史样本不足" })).toBe(
      "历史样本不足",
    );
    expect(gapLabel("insufficient_history:60d")).toBe("数据缺口待确认");
    expect(gapLabel({ code: "basis_missing" })).toBe("数据缺口待确认");
  });

  it("prefers snapshot display labels for dates and statuses", () => {
    const module = {
      snapshot: {
        module_id: "overview",
        route_path: "/macro",
        title: "总览",
        asof_date: "2026-05-20",
        asof_label: "截至 2026-05-20",
        status: "insufficient_history",
        status_label: "历史样本不足",
      },
    } as MacroModuleView;

    expect(macroAsOfLabel(module)).toBe("截至 2026-05-20");
    expect(macroStatusLabel(module)).toBe("历史样本不足");
    expect(formatMacroScalar("insufficient_history")).toBe("历史样本不足");
  });

  it("accepts v3 module fixtures without old macro module payload keys", () => {
    const module = macroModuleFixture();

    expect(module.snapshot.projection_version).toBe("macro_module_view_v3");
    expect(module.module_read.headline).toBe("美股风险：等待小盘确认");
    expect(module.module_evidence.confirmations).toHaveLength(1);
    expect(module.data_health.module_gaps).toHaveLength(1);
    expect(module.transmission).toEqual([
      {
        kind: "flow",
        label: "Yahoo",
        status: "partial",
        status_label: "部分可用",
        value: "美股风险偏好",
      },
    ]);
    expect(module).not.toHaveProperty("read");
    expect(module).not.toHaveProperty("evidence");
    expect(module).not.toHaveProperty("data_gaps");
  });

  it("labels v3 read fields without exposing backend field names", () => {
    expect(macroFieldLabel("regime_label")).toBe("宏观状态");
    expect(macroFieldLabel("confidence_label")).toBe("置信度");
    expect(macroFieldLabel("crypto_read")).toBe("加密影响");
    expect(macroFieldLabel("token_impact")).toBe("代币影响");
  });

  it("labels stale snapshots as whole-page macro data lag", () => {
    const module = macroModuleFixture({
      snapshot: {
        ...macroModuleFixture().snapshot,
        status: "stale",
        status_label: "数据滞后",
        asof_date: "2026-01-16",
        asof_label: "截至 2026-01-16",
      },
      data_health: {
        ...macroModuleFixture().data_health,
        module_gaps: [
          {
            code: "stale_latest:135d",
            label: "最新观测滞后 135 天",
          },
        ],
      },
    });

    expect(macroFreshnessAlert(module)).toEqual({
      detail: "截至 2026-01-16；宏观快照整体处于滞后状态，请先确认同步与投影状态。",
      items: ["最新观测滞后 135 天"],
      title: "宏观数据滞后",
    });
  });

  it("labels stale gap payloads as partial sequence lag instead of fact-layer lag", () => {
    const module = macroModuleFixture({
      snapshot: {
        ...macroModuleFixture().snapshot,
        status: "partial",
        status_label: "部分可用",
        asof_date: "2026-06-09",
        asof_label: "截至 2026-06-09",
      },
      data_health: {
        ...macroModuleFixture().data_health,
        summary_status: "missing",
        module_gaps: [
          {
            code: "stale_latest_8d",
            label: "最新观测已过期：8 天未更新",
          },
        ],
      },
    });

    expect(macroFreshnessAlert(module)).toEqual({
      detail: "截至 2026-06-09；页面已使用最新可用观测，少数指标仍有新鲜度缺口。",
      items: ["最新观测已过期：8 天未更新"],
      title: "部分宏观序列滞后",
    });
  });

  it("keeps global reference stale gaps in diagnostics instead of the page freshness alert", () => {
    const module = macroModuleFixture({
      snapshot: {
        ...macroModuleFixture().snapshot,
        status: "partial",
        status_label: "部分可用",
        asof_date: "2026-06-09",
        asof_label: "截至 2026-06-09",
      },
      data_health: {
        ...macroModuleFixture().data_health,
        summary_status: "ok",
        module_gaps: [],
        chart_gaps: [],
        global_gaps: [
          {
            code: "stale_latest_455d",
            label: "最新观测已过期：455 天未更新",
            scope: "global_reference",
          },
        ],
      },
    });

    expect(macroFreshnessAlert(module)).toBeNull();
  });

  it("does not show a freshness alert for fresh backend payloads", () => {
    const module = macroModuleFixture({
      snapshot: {
        ...macroModuleFixture().snapshot,
        status: "ok",
        status_label: "正常",
        asof_date: "2026-05-31",
        asof_label: "截至 2026-05-31",
      },
      data_health: {
        ...macroModuleFixture().data_health,
        module_gaps: [],
      },
    });

    expect(macroFreshnessAlert(module)).toBeNull();
  });
});
