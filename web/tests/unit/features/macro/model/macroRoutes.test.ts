import {
  MACRO_MODULE_ROUTES,
  buildMacroBreadcrumbs,
  macroNavigationPath,
  macroModuleHref,
  macroRouteLabel,
  parseMacroRouteTail,
} from "@features/macro/model/macroRoutes";
import { describe, expect, it } from "vitest";

describe("macroRoutes", () => {
  it("contains the backend module catalog in route order", () => {
    expect(MACRO_MODULE_ROUTES.map((route) => route.moduleId)).toEqual([
      "overview",
      "assets",
      "assets/equities",
      "assets/bonds",
      "assets/commodities",
      "assets/fx",
      "assets/crypto",
      "assets/crypto-derivatives",
      "rates",
      "rates/fed-funds",
      "rates/yield-curve",
      "rates/auctions",
      "rates/real-rates",
      "rates/expectations",
      "fed",
      "fed/statements",
      "fed/speeches",
      "liquidity",
      "liquidity/transmission-chain",
      "liquidity/fed-balance-sheet",
      "liquidity/operations",
      "liquidity/rrp-tga",
      "liquidity/reserves",
      "liquidity/global-dollar",
      "liquidity/subsurface",
      "economy",
      "economy/gdp",
      "economy/employment",
      "economy/inflation",
      "economy/consumer",
      "volatility",
      "volatility/dashboard",
      "volatility/vix",
      "credit",
      "credit/cds",
      "credit/stress",
    ]);
  });

  it("normalizes empty, nested, correlation, and unknown route tails", () => {
    expect(parseMacroRouteTail(undefined)).toMatchObject({
      canonicalPath: "/macro",
      moduleId: "overview",
      routeKind: "module",
    });
    expect(parseMacroRouteTail("assets/equities")).toMatchObject({
      canonicalPath: "/macro/assets/equities",
      moduleId: "assets/equities",
      routeKind: "module",
    });
    expect(parseMacroRouteTail("assets/correlation")).toMatchObject({
      canonicalPath: "/macro/assets/correlation",
      routeKind: "asset-correlation",
    });
    expect(parseMacroRouteTail("not-real")).toMatchObject({
      canonicalPath: "/macro/not-real",
      routeKind: "unsupported",
      routeTail: "not-real",
    });
  });

  it("builds canonical hrefs, labels, and breadcrumbs for nested modules", () => {
    expect(macroModuleHref("overview")).toBe("/macro");
    expect(macroModuleHref("assets/equities")).toBe("/macro/assets/equities");
    expect(macroRouteLabel("assets/equities")).toBe("美股");
    expect(macroModuleHref("liquidity/transmission-chain")).toBe(
      "/macro/liquidity/transmission-chain",
    );

    expect(buildMacroBreadcrumbs("assets/crypto-derivatives")).toEqual([
      { label: "宏观", href: "/macro" },
      { label: "大类资产", href: "/macro/assets" },
      { label: "加密衍生品", href: "/macro/assets/crypto-derivatives" },
    ]);
  });

  it("derives navigation paths from the macro navigation tree", () => {
    expect(macroNavigationPath("assets/equities").map((node) => node.label)).toEqual([
      "宏观",
      "大类资产",
      "美股",
    ]);
    expect(macroNavigationPath("assets/correlation").map((node) => node.href)).toEqual([
      "/macro",
      "/macro/assets",
      "/macro/assets/correlation",
    ]);
  });
});
