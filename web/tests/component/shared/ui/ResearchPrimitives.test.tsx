import {
  ResearchFieldGrid,
  ResearchHeader,
  ResearchMark,
  ResearchPanel,
  ResearchSection,
  ResearchTag,
} from "@shared/ui/ResearchPrimitives";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("Tracefold research primitives", () => {
  it("renders a labelled research hierarchy with source and state semantics", () => {
    render(
      <ResearchPanel aria-label="selected research object">
        <ResearchHeader
          badge={<ResearchTag tone="info">Source facts</ResearchTag>}
          eyebrow="research dossier"
          subtitle="Strict facts only"
          title="Alpha"
        />
        <ResearchSection title="Object facts">
          <ResearchMark label="alpha" />
          <ResearchFieldGrid
            fields={[
              {
                detail: "Official source",
                label: "Identity",
                source: "official",
                tone: "health",
                value: "alpha.io",
              },
            ]}
          />
        </ResearchSection>
      </ResearchPanel>,
    );

    expect(screen.getByRole("region", { name: "selected research object" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alpha" })).toBeInTheDocument();
    expect(screen.getByText("official")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });
});
