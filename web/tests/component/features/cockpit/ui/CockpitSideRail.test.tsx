import { CockpitSideRail } from "@features/cockpit";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

describe("CockpitSideRail", () => {
  it("renders accessible navigation, filters, and watchlist rows", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <CockpitSideRail
          tokenItemsCount={2}
          scope="all"
          onScopeChange={vi.fn()}
          handles="toly"
          onHandlesChange={vi.fn()}
          onWindowChange={vi.fn()}
          decisionCounts={{ driver: 1, watch: 1, investigate: 0, discard: 0 }}
          watchlistRows={[{ handle: "toly", lastSeenAtMs: 1_700_000_000_000, unreadCount: 2 }]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /Radar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Stocks/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ops/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Watchlist/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Signal Pulse/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("watchlist handles")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /toly/i })).toHaveAttribute(
      "href",
      "/watchlist?handle=toly",
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
