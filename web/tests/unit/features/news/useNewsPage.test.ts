import {
  agentBriefLabel,
  agentBriefMissingText,
  formatAgentBriefStrength,
  inferNewsInstruments,
} from "@features/news/newsViewModel";
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

  it("formats agent brief state without turning it into a trading decision", () => {
    expect(agentBriefLabel("insufficient")).toBe("insufficient");
    expect(agentBriefMissingText({ status: "pending" })).toBe("Agent brief pending.");
    expect(formatAgentBriefStrength("moderate")).toBe("moderate");
  });

  it("builds instrument display only from persisted token lanes", () => {
    const instruments = inferNewsInstruments({
      token_lanes: [
        {
          lane: "attention",
          resolution_status: "unknown_attention",
          symbol: "NEWX",
        },
      ],
    }).map((instrument) => instrument.label);

    expect(instruments).toEqual(["NEWX"]);
  });
});
