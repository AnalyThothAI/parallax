import {
  requireMacroAssetCorrelationData,
  requireMacroModuleView,
  requireMacroSeriesData,
} from "@features/macro/model/macroCurrentContract";
import {
  macroCorrelationFixture,
  macroModuleFixture,
  macroSeriesFixture,
} from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroCurrentContract", () => {
  it("accepts the canonical current module, series, and correlation fixtures", () => {
    expect(requireMacroModuleView(macroModuleFixture())).toBeTruthy();
    expect(requireMacroSeriesData(macroSeriesFixture())).toBeTruthy();
    expect(requireMacroAssetCorrelationData(macroCorrelationFixture())).toBeTruthy();
  });

  it("rejects a module payload without current data health", () => {
    const payload = { ...macroModuleFixture() } as Record<string, unknown>;
    delete payload.data_health;

    expect(() => requireMacroModuleView(payload)).toThrowError(
      "macro_current_contract:module.data_health",
    );
  });

  it("rejects a module chart without canonical series or min_points", () => {
    const missingSeries = macroModuleFixture();
    missingSeries.primary_chart = { ...missingSeries.primary_chart };
    delete missingSeries.primary_chart.series;

    expect(() => requireMacroModuleView(missingSeries)).toThrowError(
      "macro_current_contract:primary_chart.series",
    );

    const missingMinimum = macroModuleFixture();
    missingMinimum.primary_chart = { ...missingMinimum.primary_chart };
    delete missingMinimum.primary_chart.min_points;

    expect(() => requireMacroModuleView(missingMinimum)).toThrowError(
      "macro_current_contract:primary_chart.min_points",
    );
  });

  it("rejects a returned series payload without points instead of treating it as empty", () => {
    const payload = macroSeriesFixture();
    delete payload.series["asset:spx"]?.points;

    expect(() => requireMacroSeriesData(payload)).toThrowError(
      "macro_current_contract:series_data.series.asset:spx.points",
    );
  });

  it("rejects a correlation payload without the canonical pair collection", () => {
    const payload = { ...macroCorrelationFixture() } as Record<string, unknown>;
    delete payload.pairs;

    expect(() => requireMacroAssetCorrelationData(payload)).toThrowError(
      "macro_current_contract:correlation_data.pairs",
    );
  });
});
