import {
  hiddenMacroDirectRoutes,
  macroRouteDescriptor,
  supportedMacroAuditRoutes,
} from "@features/macro/model/macroPageRegistry";
import { describe, expect, it } from "vitest";

describe("macroPageRegistry", () => {
  it("keeps the supported audit route catalog aligned with addressable macro pages", () => {
    expect(supportedMacroAuditRoutes).toHaveLength(32);
    expect(macroRouteDescriptor("assets/correlation")).toEqual({
      href: "/macro/assets/correlation",
      label: "相关性",
      pageKind: "matrix",
      productTier: "primary",
      routeId: "assets/correlation",
    });
  });

  it("keeps hidden-supported direct routes addressable but out of primary nav", () => {
    expect(hiddenMacroDirectRoutes.map((route) => route.href)).toEqual([
      "/macro/rates/auctions",
      "/macro/fed/statements",
      "/macro/fed/speeches",
      "/macro/volatility/dashboard",
      "/macro/credit/cds",
    ]);
  });
});
