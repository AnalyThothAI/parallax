import {
  flattenMacroRouteDescriptors,
  supportedMacroAuditRoutes,
} from "@features/macro/model/macroPageRegistry";
import { describe, expect, it } from "vitest";

describe("macroPageRegistry", () => {
  it("keeps the supported audit route catalog aligned with addressable macro pages", () => {
    expect(supportedMacroAuditRoutes).toHaveLength(16);
    expect(supportedMacroAuditRoutes.map((route) => route.href)).not.toContain(
      "/macro/assets/correlation",
    );
  });

  it("hard deletes weak routes instead of keeping hidden direct routes", () => {
    expect(supportedMacroAuditRoutes.map((route) => route.href)).not.toEqual(
      expect.arrayContaining([
        "/macro/assets/crypto-derivatives",
        "/macro/assets/correlation",
        "/macro/rates/auctions",
        "/macro/rates/expectations",
        "/macro/fed/statements",
        "/macro/fed/speeches",
        "/macro/liquidity/global-dollar",
        "/macro/liquidity/reserves",
        "/macro/liquidity/subsurface",
        "/macro/liquidity/transmission-chain",
        "/macro/liquidity/operations",
        "/macro/liquidity/fed-balance-sheet",
        "/macro/economy/consumer",
        "/macro/volatility/dashboard",
        "/macro/credit/cds",
      ]),
    );
  });

  it("throws when an addressable macro node is only partially annotated", () => {
    let message = "";
    try {
      flattenMacroRouteDescriptors([{ label: "Bad", href: "/macro/bad", routeId: "overview" }]);
    } catch (error) {
      message = error instanceof Error ? error.message : String(error);
    }

    expect(message).toContain("/macro/bad");
    expect(message).toContain("Bad");
  });
});
