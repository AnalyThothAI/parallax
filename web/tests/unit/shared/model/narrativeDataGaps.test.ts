import { narrativeGapLabel } from "@shared/model/narrativeDataGaps";
import { describe, expect, it } from "vitest";

describe("narrativeDataGaps", () => {
  it("labels current narrative admission gaps", () => {
    expect(narrativeGapLabel({ reason: "no_current_admission" })).toBe("not admitted");
    expect(narrativeGapLabel({ reason: "suppressed" })).toBe("suppressed");
    expect(narrativeGapLabel({ reason: "unsupported_window" })).toBe("admission unsupported");
    expect(narrativeGapLabel({ reason: "narrative_not_supported_for_window" })).toBe(
      "admission unsupported",
    );
    expect(narrativeGapLabel({ reason: "out_of_frontier" })).toBe("out of current frontier");
  });

  it("normalizes unknown gaps without inventing compatibility labels", () => {
    expect(narrativeGapLabel({ reason: "provider_gap" })).toBe("provider gap");
  });
});
