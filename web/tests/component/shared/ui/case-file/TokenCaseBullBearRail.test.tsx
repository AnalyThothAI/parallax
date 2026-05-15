import { buildTokenCaseViewModel } from "@features/token-case";
import { TokenCaseBullBearRail } from "@shared/ui/case-file/TokenCaseBullBearRail";
import { render, screen } from "@testing-library/react";
import { tokenCaseFixture } from "@tests/fixtures/tokenCaseFixture";
import { describe, expect, it } from "vitest";

describe("TokenCaseBullBearRail", () => {
  it("keeps bull and bear headings when thesis content is missing", () => {
    const vm = buildTokenCaseViewModel({
      dossier: tokenCaseFixture(),
      route: { window: "1h", scope: "all", postSort: "catalyst" },
    });

    render(
      <TokenCaseBullBearRail
        bullBear={{
          ...vm.bullBear,
          bull: { ...vm.bullBear.bull, thesis: "", bullets: [] },
          bear: { ...vm.bullBear.bear, thesis: "", bullets: [] },
        }}
      />,
    );

    expect(screen.getByText("尚无 bull/bear 评估")).toBeInTheDocument();
    expect(screen.getByText("Bull · 多头")).toBeInTheDocument();
    expect(screen.getByText("Bear · 空头")).toBeInTheDocument();
  });
});
