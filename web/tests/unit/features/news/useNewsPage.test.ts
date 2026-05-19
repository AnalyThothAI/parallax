import { inferNewsInstruments, newsNextAction, newsRouteState } from "@features/news/newsViewModel";
import { newsLifecycleLabel, newsTokenLaneLabel } from "@shared/model/newsIntel";
import { describe, expect, it } from "vitest";

describe("newsIntel model", () => {
  it("labels attention lifecycle explicitly", () => {
    expect(newsLifecycleLabel("attention")).toBe("Attention");
  });

  it("labels unknown token lane without pretending it is resolved", () => {
    expect(
      newsTokenLaneLabel({
        lane: "attention",
        resolution_status: "unknown_attention",
        symbol: "NEWX",
      }),
    ).toBe("NEWX · attention");
  });

  it("keeps semantic news gated when token identity is missing", () => {
    const row = {
      fact_lanes: [{ event_type: "regulatory", status: "attention" }],
      headline: "SEC expands tokenized stock review",
      summary: "Policy backdrop without resolved venue identity",
      token_lanes: [],
    };

    expect(newsRouteState(row)).toBe("identity missing");
    expect(newsNextAction(row)).toBe("Resolve target identity");
  });

  it("infers tradable instruments from item text before a production quote exists", () => {
    const instruments = inferNewsInstruments({
      headline: "World Liberty Financial treasury company AI Financial warns in SEC filing",
      summary: "The filing may affect WLFI sentiment.",
      token_lanes: [],
    }).map((instrument) => instrument.label);

    expect(instruments).toContain("WLFI");
    expect(instruments).toContain("AI Financial");
  });
});
