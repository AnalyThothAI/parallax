import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import {
  ObsidianActionBar,
  ObsidianCase,
  ObsidianCaseHeader,
  ObsidianEvidenceList,
  ObsidianField,
  ObsidianFieldGrid,
  ObsidianPill,
  ObsidianSection,
  ObsidianTokenMark,
} from "./obsidian";

describe("Obsidian UI language", () => {
  it("renders a source-labelled desk case without accessibility violations", async () => {
    const { container } = render(
      <ObsidianCase aria-label="selected case">
        <ObsidianCaseHeader
          actions={
            <ObsidianActionBar>
              <a href="/search?q=alpha">Search Intel</a>
              <button type="button">Mark reviewed</button>
            </ObsidianActionBar>
          }
          badge={<ObsidianPill tone="agent">Agent memo</ObsidianPill>}
          eyebrow="selected case"
          mark={<ObsidianTokenMark label="alpha" />}
          subtitle="Official facts, community proof, narrative, market and decision in one file."
          title="$ALPHA"
        />

        <ObsidianSection subtitle="Profile facts stay separate from agent text." title="Identity">
          <ObsidianFieldGrid>
            <ObsidianField label="Official" source="official" value="alpha.io" />
            <ObsidianField
              detail="12 watchlist accounts mentioned it in the active window."
              label="Community"
              source="social"
              tone="health"
              value="12 handles"
            />
            <ObsidianField
              detail="Resolver confidence 91%"
              label="Market"
              source="deterministic"
              tone="info"
              value="$18.2M volume"
            />
          </ObsidianFieldGrid>
        </ObsidianSection>

        <ObsidianSection title="Evidence">
          <ObsidianEvidenceList
            items={[
              {
                body: "Founder account posted the contract and the community echoed it.",
                href: "/search?q=alpha",
                id: "ev-1",
                meta: "12m ago",
                title: "Official plus community confirmation",
                tone: "opportunity",
              },
            ]}
          />
        </ObsidianSection>
      </ObsidianCase>,
    );

    expect(screen.getByRole("region", { name: "selected case" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "$ALPHA" })).toBeInTheDocument();
    expect(screen.getByText("Agent memo")).toBeInTheDocument();

    const identity = screen.getByRole("region", { name: "Identity" });
    expect(within(identity).getByText("Official")).toBeInTheDocument();
    expect(within(identity).getByText("alpha.io")).toBeInTheDocument();
    expect(within(identity).getByText("official")).toBeInTheDocument();
    expect(within(identity).getByText("social")).toBeInTheDocument();
    expect(within(identity).getByText("deterministic")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Search Intel" })).toHaveAttribute(
      "href",
      "/search?q=alpha",
    );
    expect(screen.getByRole("button", { name: "Mark reviewed" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Official plus community confirmation" }),
    ).toHaveAttribute("href", "/search?q=alpha");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders stable empty evidence and data-driven fields", () => {
    render(
      <ObsidianCase>
        <ObsidianSection title="Narrative">
          <ObsidianFieldGrid
            fields={[
              {
                detail: "No agent memo available.",
                label: "Thesis",
                source: "agent",
                tone: "neutral",
                value: "Unavailable",
              },
            ]}
          />
        </ObsidianSection>
        <ObsidianSection title="Evidence">
          <ObsidianEvidenceList emptyLabel="No source events in this window." items={[]} />
        </ObsidianSection>
      </ObsidianCase>,
    );

    expect(screen.getByText("Thesis")).toBeInTheDocument();
    expect(screen.getByText("agent")).toBeInTheDocument();
    expect(screen.getByText("No source events in this window.")).toBeInTheDocument();
  });
});
