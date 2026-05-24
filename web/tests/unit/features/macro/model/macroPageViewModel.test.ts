import {
  formatMacroScalar,
  gapLabel,
  macroAsOfLabel,
  macroFieldLabel,
  macroStatusLabel,
} from "@features/macro/model/macroPageViewModel";
import type { MacroModuleView } from "@lib/types";
import { describe, expect, it } from "vitest";

describe("macroPageViewModel", () => {
  it("uses display-ready v2 labels and never surfaces raw gap strings", () => {
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

  it("labels v2 read fields without exposing backend field names", () => {
    expect(macroFieldLabel("regime_label")).toBe("宏观状态");
    expect(macroFieldLabel("confidence_label")).toBe("置信度");
    expect(macroFieldLabel("crypto_read")).toBe("加密影响");
    expect(macroFieldLabel("token_impact")).toBe("代币影响");
  });
});
