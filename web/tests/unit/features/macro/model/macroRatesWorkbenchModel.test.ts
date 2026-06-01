import {
  buildRatesWorkbenchView,
  humanizeRatesConceptKey,
  humanizeRatesGapCode,
  isRatesModuleId,
} from "@features/macro/model/macroRatesWorkbenchModel";
import {
  macroAuctionsOfficialModuleFixture,
  macroAuctionsProxyModuleFixture,
  macroExpectationsOfficialModuleFixture,
  macroExpectationsProxyModuleFixture,
  macroFedFundsModuleFixture,
  macroRealRatesModuleFixture,
} from "@tests/fixtures/macroFixture";
import { describe, expect, it } from "vitest";

describe("macroRatesWorkbenchModel", () => {
  it("identifies rates module ids", () => {
    expect(isRatesModuleId("rates/fed-funds")).toBe(true);
    expect(isRatesModuleId("assets/equities")).toBe(false);
  });

  it("builds proxy workbench copy without leaking raw auction gap codes or concepts", () => {
    const auctions = buildRatesWorkbenchView(macroAuctionsProxyModuleFixture(), "rates/auctions");

    expect(auctions.readiness).toBe("proxy");
    expect(auctions.marketHeadline).toContain("当前为拍卖代理页面");
    expect(auctions.marketHeadline).not.toContain("treasury_auction_results_missing");
    expect(auctions.marketExplanation).not.toContain("rates:dgs10");
    expect(primaryWorkbenchText(auctions)).not.toMatch(
      /treasury_auction_(calendar|results)_missing|rates:dgs10/,
    );
  });

  it("builds proxy expectations copy without leaking raw policy path gaps", () => {
    const expectations = buildRatesWorkbenchView(
      macroExpectationsProxyModuleFixture(),
      "rates/expectations",
    );

    expect(expectations.readiness).toBe("proxy");
    expect(expectations.marketHeadline).toContain("当前为政策路径代理页面");
    expect(expectations.marketHeadline).not.toContain("fomc_probability_feed_missing");
    expect(primaryWorkbenchText(expectations)).not.toMatch(
      /fed_funds_futures_missing|fomc_probability_feed_missing/,
    );
  });

  it("preserves backend data notes as market explanation copy", () => {
    const fedFunds = {
      ...macroFedFundsModuleFixture(),
      module_read: {
        headline: "联邦基金走廊：后台说明可用",
        data_note: "后台数据说明：EFFR 与目标区间均来自官方观测。",
      },
    };

    const view = buildRatesWorkbenchView(fedFunds, "rates/fed-funds");

    expect(view.marketExplanation).toBe("后台数据说明：EFFR 与目标区间均来自官方观测。");
  });

  it("preserves backend methodology notes as market explanation copy", () => {
    const fedFunds = {
      ...macroFedFundsModuleFixture(),
      module_read: {
        headline: "联邦基金走廊：方法说明可用",
        methodology_note: "方法说明：优先读取政策走廊，再检查隔夜融资偏离。",
      },
    };

    const view = buildRatesWorkbenchView(fedFunds, "rates/fed-funds");

    expect(view.marketExplanation).toBe("方法说明：优先读取政策走廊，再检查隔夜融资偏离。");
  });

  it("selects official auction tables before proxy yield tables", () => {
    const officialAuctions = buildRatesWorkbenchView(
      macroAuctionsOfficialModuleFixture(),
      "rates/auctions",
    );

    expect(officialAuctions.readiness).toBe("ready");
    expect(officialAuctions.detailTables[0]?.table.title).toContain("未来拍卖");
    expect(officialAuctions.detailTables[0]?.table.id).not.toContain("proxy");
  });

  it("keeps auction modules partial when only one official table is present", () => {
    const officialAuctions = macroAuctionsOfficialModuleFixture();
    const calendarOnlyAuctions = {
      ...officialAuctions,
      tables: officialAuctions.tables.filter((table) => table.id !== "treasury_auction_results"),
      data_health: {
        ...officialAuctions.data_health,
        summary_status: "partial",
        summary_label: "官方拍卖日历可用，结果待接入",
        future_integration_gaps: [
          {
            code: "treasury_auction_results_missing",
            label: "官方拍卖结果尚未入库",
            severity: "warning",
          },
        ],
      },
    };

    const view = buildRatesWorkbenchView(calendarOnlyAuctions, "rates/auctions");

    expect(view.readiness).toBe("partial");
    expect(view.marketHeadline).not.toContain("当前为拍卖代理页面");
    expect(view.detailTables[0]?.table.title).toContain("未来拍卖");
    expect(view.detailTables[0]?.table.id).not.toContain("proxy");
  });

  it("selects official expectations probability tables before proxy tables", () => {
    const officialExpectations = buildRatesWorkbenchView(
      macroExpectationsOfficialModuleFixture(),
      "rates/expectations",
    );

    expect(officialExpectations.readiness).toBe("ready");
    expect(officialExpectations.detailTables[0]?.table.title).toContain("会议概率");
    expect(officialExpectations.detailTables[0]?.table.id).not.toContain("proxy");
  });

  it("keeps expectations modules partial when probability table exists with a future gap", () => {
    const officialExpectations = macroExpectationsOfficialModuleFixture();
    const probabilityWithGap = {
      ...officialExpectations,
      data_health: {
        ...officialExpectations.data_health,
        summary_status: "partial",
        summary_label: "会议概率可用，期货曲线待接入",
        future_integration_gaps: [
          {
            code: "fed_funds_futures_missing",
            label: "联邦基金期货数据尚未入库",
            severity: "warning",
          },
        ],
      },
    };

    const view = buildRatesWorkbenchView(probabilityWithGap, "rates/expectations");

    expect(view.readiness).toBe("partial");
    expect(view.marketHeadline).not.toContain("当前为政策路径代理页面");
    expect(view.detailTables[0]?.table.title).toContain("会议概率");
    expect(view.detailTables[0]?.table.id).not.toContain("proxy");
  });

  it("humanizes rates keys and builds neutral ready module facts", () => {
    const fedFunds = buildRatesWorkbenchView(macroFedFundsModuleFixture(), "rates/fed-funds");
    const realRates = buildRatesWorkbenchView(macroRealRatesModuleFixture(), "rates/real-rates");

    expect(humanizeRatesConceptKey("rates:dgs10")).toBe("10年期美债收益率");
    expect(humanizeRatesGapCode("fomc_probability_feed_missing")).toBe("FOMC 概率数据尚未入库");
    expect(fedFunds.facts.map((fact) => fact.label)).toContain("EFFR");
    expect(realRates.marketHeadline).toContain("实际利率");
    expect(primaryWorkbenchText(fedFunds)).not.toContain("fed:effr");
  });
});

function primaryWorkbenchText(view: {
  title: string;
  question: string;
  marketHeadline: string;
  marketExplanation: string;
  facts: Array<{
    interpretation: string | null;
    label: string;
    observedAtLabel: string;
    sourceLabel: string | null;
    statusLabel: string | null;
    value: string;
  }>;
  missingPrimaryItems: string[];
  proxyNote: string | null;
  chartTitle: string;
  chartNote: string | null;
  decisionGroups: Array<{ items: Array<{ detail: string; label: string }>; label: string }>;
}): string {
  return [
    view.title,
    view.question,
    view.marketHeadline,
    view.marketExplanation,
    view.proxyNote,
    view.chartTitle,
    view.chartNote,
    ...view.missingPrimaryItems,
    ...view.facts.flatMap((fact) => [
      fact.label,
      fact.value,
      fact.observedAtLabel,
      fact.sourceLabel,
      fact.statusLabel,
      fact.interpretation,
    ]),
    ...view.decisionGroups.flatMap((group) => [
      group.label,
      ...group.items.flatMap((item) => [item.label, item.detail]),
    ]),
  ]
    .filter(Boolean)
    .join("\n");
}
