import { buildTokenCaseViewModel } from "@features/token-case";
import { TokenCasePanel } from "@shared/ui/case-file";
import { render, screen } from "@testing-library/react";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it, vi } from "vitest";

describe("TokenCasePanel", () => {
  it("renders the shared token case anatomy", () => {
    const vm = buildTokenCaseViewModel({
      dossier: tokenCaseFixture(),
      route: { window: "1h", scope: "all", postSort: "catalyst" },
    });

    render(
      <TokenCasePanel
        vm={vm}
        onLoadMorePosts={vi.fn()}
        onScopeChange={vi.fn()}
        onTimelineSortChange={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: /Token case/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /\$HANSA/i })).toBeInTheDocument();
    expect(screen.getByText("Mention Timeline")).toBeInTheDocument();
    expect(screen.getByText("Live Market")).toBeInTheDocument();
    expect(screen.getByText("Data Gaps")).toBeInTheDocument();
    expect(screen.getAllByText(/原文/)[0]).toBeInTheDocument();
  });

  it("renders CEX derivatives when a detail snapshot is present", () => {
    const dossier = tokenCaseFixture();
    const vm = buildTokenCaseViewModel({
      dossier: {
        ...dossier,
        target: {
          ...dossier.target,
          target_type: "CexToken",
          target_id: "cex_token:BTC",
          symbol: "BTC",
          chain_id: null,
          address: null,
        },
        cex_detail: {
          target_type: "CexToken",
          target_id: "cex_token:BTC",
          exchange: "binance",
          native_market_id: "BTCUSDT",
          status: "ready",
          baseline_status: "ready",
          coinglass_status: "ready",
          mark_price: 67_050,
          funding_rate: 0.0001,
          volume_24h_usd: 12_400_000,
          open_interest_usd: 98_000_000,
          oi_change_pct_24h: 3.5,
          cvd_delta_4h: -1_250_000,
          level_bands: [{ kind: "resistance", price: 72_000, score: 0.82 }],
          degraded_reasons: [],
          source_refs: [{ ref_id: "metric:cex:open_interest_usd:BTCUSDT" }],
          observed_at_ms: 1_777_746_000_000,
          computed_at_ms: 1_777_746_030_000,
        },
      },
      route: { window: "1h", scope: "all", postSort: "catalyst" },
    });

    render(
      <TokenCasePanel
        vm={vm}
        onLoadMorePosts={vi.fn()}
        onScopeChange={vi.fn()}
        onTimelineSortChange={vi.fn()}
        onWindowChange={vi.fn()}
      />,
    );

    expect(screen.getByText("CEX Derivatives")).toBeInTheDocument();
    expect(screen.getByText("Binance · BTCUSDT")).toBeInTheDocument();
    expect(screen.getByText("OI 24h")).toBeInTheDocument();
    expect(screen.getByText("+3.5%")).toBeInTheDocument();
    expect(screen.getByText("resistance")).toBeInTheDocument();
  });
});
