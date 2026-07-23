import { MacroEvidenceCard, MacroUnavailableList } from "@features/macro";
import {
  MacroCorrelationList,
  MacroInflationReleaseList,
} from "@features/macro/ui/MacroDomainBlocks";
import { screen } from "@testing-library/react";
import {
  macroCrossAssetFixture,
  macroLiquidityFundingFixture,
  macroRatesInflationFixture,
} from "@tests/fixtures/macroFixture";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { describe, expect, it } from "vitest";

describe("Macro evidence primitives", () => {
  it("keeps value, unit, freshness, sample and derivation visible without hover", () => {
    const item = macroLiquidityFundingFixture().net_liquidity;
    renderWithProviders(<MacroEvidenceCard item={item} />);

    expect(screen.getByText("净流动性会计代理")).toBeInTheDocument();
    expect(screen.getAllByText("derived:net_liquidity_accounting_proxy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("millions_usd").length).toBeGreaterThan(0);
    expect(screen.getByText(/观测年龄 0 天 · 过期阈值 8 天/)).toBeInTheDocument();
    expect(screen.getByText(/2026-04-29 → 2026-07-22 · 60 个样本/)).toBeInTheDocument();
    expect(screen.getByText(/accounting proxy only: Fed assets/)).toBeInTheDocument();
    expect(screen.getAllByText(/source_unit=/)).toHaveLength(3);
  });

  it("states that unavailable capabilities are not assessed and not scored", () => {
    renderWithProviders(
      <MacroUnavailableList
        items={[
          {
            capability: "etf_premium_discount",
            reason: "source_not_ingested",
            status: "not_assessed",
          },
        ]}
      />,
    );

    expect(screen.getByText("债券 ETF 折溢价")).toBeInTheDocument();
    expect(screen.getByText("etf_premium_discount")).toBeInTheDocument();
    expect(screen.getByText("未评估 · 不计分")).toBeInTheDocument();
    expect(screen.getByText("数据源尚未接入")).toBeInTheDocument();
    expect(screen.getByText("source_not_ingested")).toBeInTheDocument();
  });

  it("uses Chinese window and unit labels while retaining raw codes as secondary evidence", () => {
    const correlation = macroCrossAssetFixture().correlations_20[0];
    const inflation = macroRatesInflationFixture().inflation_releases[0];
    renderWithProviders(
      <>
        <MacroCorrelationList items={[correlation]} title="相关性" />
        <MacroInflationReleaseList items={[inflation]} />
      </>,
    );

    expect(screen.getAllByText("20 个交易日").length).toBeGreaterThan(0);
    expect(screen.getAllByText("20_sessions").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/百分比/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("percent").length).toBeGreaterThan(0);
  });

  it("fails closed when a release unit is outside the display vocabulary", () => {
    const inflation = macroRatesInflationFixture().inflation_releases[0];
    renderWithProviders(
      <MacroInflationReleaseList
        items={[
          {
            ...inflation,
            release_change: { ...inflation.release_change, unit: "new_unit" as never },
          },
        ]}
      />,
    );

    expect(screen.getByText(/未识别单位/)).toBeInTheDocument();
    expect(screen.getByText("new_unit")).toBeInTheDocument();
  });
});
