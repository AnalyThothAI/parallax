import type { TokenFlowItem } from "@lib/types";
import { tokenSearchQuery } from "@shared/routing/tokenSearch";
import { describe, expect, it } from "vitest";

describe("tokenSearchQuery", () => {
  it("prefers deterministic contract identity over symbol aliases", () => {
    expect(
      tokenSearchQuery(
        tokenIdentity({
          address: "0xf280b1912bb86f5198e94e0f42f73e00b4694126",
          symbol: "ASTEROID",
        }),
      ),
    ).toBe("0xf280b1912bb86f5198e94e0f42f73e00b4694126");
  });

  it("uses the CEX instrument id before falling back to symbol search", () => {
    expect(tokenSearchQuery(tokenIdentity({ inst_id: "BTC-USDT", symbol: "BTC" }))).toBe(
      "BTC-USDT",
    );
  });
});

function tokenIdentity(identity: Partial<TokenFlowItem["identity"]>): TokenFlowItem {
  return {
    identity: {
      identity_key: "asset:test",
      identity_status: "EXACT",
      ...identity,
    },
  } as TokenFlowItem;
}
