import { TokenIntelHeader } from "@shared/ui/TokenIntelHeader";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("TokenIntelHeader", () => {
  it("carries profile links and core token facts in one shared header", () => {
    render(
      <TokenIntelHeader
        ariaLabel="Token intelligence case"
        eyebrow="token intelligence"
        fields={[
          {
            detail: "12 posts · 10 authors",
            label: "Community",
            source: "social",
            value: "12 posts",
          },
          {
            detail: "profile ready",
            label: "Official",
            source: "official",
            value: "Asteroid Shiba",
          },
        ]}
        meta={<span>score 90</span>}
        profile={{
          status: "ready",
          provider: "gmgn_dex_profile",
          identity: {
            symbol: "ASTEROID",
            name: "Asteroid Shiba",
          },
          links: {
            website_url: "https://asteroideth.io/",
            twitter_url: "https://x.com/MascotAsteroid",
          },
        }}
        profileLabel="Official profile for $ASTEROID"
        subtitle="eip155:1 · 0xf280b1...694126"
        title="$ASTEROID"
      />,
    );

    const header = screen.getByRole("region", { name: "Token intelligence case" });
    expect(within(header).getByRole("heading", { name: "$ASTEROID" })).toBeInTheDocument();
    expect(
      within(header).getByRole("region", { name: "Official profile for $ASTEROID" }),
    ).toBeInTheDocument();
    expect(within(header).getByRole("link", { name: "Website" })).toHaveAttribute(
      "href",
      "https://asteroideth.io/",
    );
    expect(within(header).getByRole("link", { name: "X" })).toHaveAttribute(
      "href",
      "https://x.com/MascotAsteroid",
    );
    expect(within(header).getByText("Community")).toBeInTheDocument();
    expect(within(header).getByText("Official")).toBeInTheDocument();
  });
});
