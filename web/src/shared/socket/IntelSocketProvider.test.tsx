import { describe, expect, it } from "vitest";

import { normalizeMarketTargets } from "./marketTargets";

describe("IntelSocketProvider", () => {
  it("normalizes market targets deterministically", () => {
    expect(
      normalizeMarketTargets([
        { target_type: "Asset", target_id: "b" },
        { target_type: "Asset", target_id: "a" },
        { target_type: "Asset", target_id: "a" },
        { target_type: "", target_id: "missing" },
        { target_type: "Asset", target_id: null },
      ]),
    ).toEqual([
      { target_type: "Asset", target_id: "a" },
      { target_type: "Asset", target_id: "b" },
    ]);
  });
});
