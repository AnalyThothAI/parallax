import { buildTokenCaseViewModel } from "@features/token-case";
import { TokenCaseMarketRail } from "@shared/ui/case-file/TokenCaseMarketRail";
import { render, screen } from "@testing-library/react";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

describe("TokenCaseMarketRail", () => {
  it("renders degraded market readiness labels", () => {
    const vm = buildTokenCaseViewModel({
      dossier: tokenCaseFixture(),
      route: { window: "1h", scope: "all", postSort: "catalyst" },
    });

    render(<TokenCaseMarketRail market={vm.market} />);

    expect(screen.getByText("pricefeed route")).toBeInTheDocument();
    expect(screen.getByText("WS subscription")).toBeInTheDocument();
    expect(screen.getByText("OHLC")).toBeInTheDocument();
  });
});
