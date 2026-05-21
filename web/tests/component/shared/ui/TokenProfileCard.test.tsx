import type { TokenProfileBlock } from "@lib/types";
import { TokenProfileCard } from "@shared/ui/TokenProfileCard";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

const TOKEN_IMAGE_URL = "/api/token-images/zec-local";

afterEach(() => cleanup());

describe("TokenProfileCard", () => {
  it("renders ready profile links and description", () => {
    render(<TokenProfileCard profile={readyProfile()} />);

    expect(screen.getByText("Zcash")).toBeInTheDocument();
    expect(screen.getByText("$ZEC")).toBeInTheDocument();
    expect(screen.getByText("Privacy coin profile facts.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Zcash logo" })).toHaveAttribute(
      "src",
      TOKEN_IMAGE_URL,
    );

    expectLink("Website", "https://z.cash");
    expectLink("X", "https://x.com/zcash");
    expectLink("Telegram", "https://t.me/zcash");
    expectLink("GMGN", "https://gmgn.ai/cex/ZEC");
    expectLink("GeckoTerminal", "https://www.geckoterminal.com/zec");
  });

  it("derives an X link from twitter_username when twitter_url is absent", () => {
    render(
      <TokenProfileCard
        profile={{
          ...readyProfile(),
          links: {
            twitter_url: null,
            twitter_username: "zcash",
          },
        }}
      />,
    );

    expectLink("X", "https://x.com/zcash");
    expect(screen.getByText("@zcash")).toBeInTheDocument();
  });

  it("renders pending, missing, and error states", () => {
    const { rerender } = render(<TokenProfileCard compact profile={stateProfile("pending")} />);
    expect(screen.getByText("profile pending")).toBeInTheDocument();

    rerender(<TokenProfileCard compact profile={stateProfile("missing")} />);
    expect(screen.getByText("profile not found")).toBeInTheDocument();

    rerender(
      <TokenProfileCard
        compact
        profile={{
          ...stateProfile("error"),
          source: { provider: "gmgn", raw_available: false, last_error: "gmgn timeout" },
        }}
      />,
    );
    expect(screen.getByText("profile refresh error")).toBeInTheDocument();
    expect(screen.getByText("gmgn timeout")).toBeInTheDocument();
  });
});

function expectLink(name: string, href: string) {
  const link = screen.getByRole("link", { name });
  expect(link).toHaveAttribute("href", href);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noreferrer");
}

function readyProfile(): TokenProfileBlock {
  return {
    status: "ready",
    provider: "gmgn",
    observed_at_ms: 1_778_426_440_000,
    identity: {
      symbol: "ZEC",
      name: "Zcash",
      logo_url: TOKEN_IMAGE_URL,
      banner_url: "https://cdn.example.test/zec-banner.png",
      description: "Privacy coin profile facts.",
    },
    links: {
      website_url: "https://z.cash",
      twitter_url: "https://x.com/zcash",
      twitter_username: "zcash",
      telegram_url: "https://t.me/zcash",
      gmgn_url: "https://gmgn.ai/cex/ZEC",
      geckoterminal_url: "https://www.geckoterminal.com/zec",
    },
    source: {
      provider: "gmgn",
      raw_available: true,
      last_error: null,
    },
  };
}

function stateProfile(status: string): TokenProfileBlock {
  return {
    status,
    provider: "gmgn",
    observed_at_ms: null,
    identity: null,
    links: null,
    source: null,
  };
}
