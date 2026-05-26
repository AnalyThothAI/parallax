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
      "assets/equities",
      "assets/bonds",
      "assets/commodities",
      "assets/fx",
      "assets/crypto",
      "assets/crypto-derivatives",
      "rates/fed-funds",
      "rates/yield-curve",
      "rates/auctions",
      "rates/real-rates",
      "rates/expectations",
      "fed/statements",
      "fed/speeches",
      "liquidity/transmission-chain",
      "liquidity/fed-balance-sheet",
      "liquidity/operations",
      "liquidity/rrp-tga",
      "liquidity/reserves",
      "liquidity/global-dollar",
      "liquidity/subsurface",
      "economy/gdp",
      "economy/employment",
      "economy/inflation",
      "economy/consumer",
      "volatility/dashboard",
      "volatility/vix",
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
      pageKind: "matrix",
      productTier: "primary",
      routeId: "assets/correlation",
      routeKind: "matrix",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("assets")).toMatchObject({
      canonicalPath: "/macro/assets/equities",
      routeKind: "redirect",
      routeTail: "assets",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("rates")).toMatchObject({
      canonicalPath: "/macro/rates/fed-funds",
      routeKind: "redirect",
      routeTail: "rates",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("fed")).toMatchObject({
      canonicalPath: "/macro/fed/statements",
      routeKind: "redirect",
      routeTail: "fed",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("liquidity")).toMatchObject({
      canonicalPath: "/macro/liquidity/transmission-chain",
      routeKind: "redirect",
      routeTail: "liquidity",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("economy")).toMatchObject({
      canonicalPath: "/macro/economy/gdp",
      routeKind: "redirect",
      routeTail: "economy",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("volatility")).toMatchObject({
      canonicalPath: "/macro/volatility/dashboard",
      routeKind: "redirect",
      routeTail: "volatility",
      wasUnknown: false,
    });
    expect(parseMacroRouteTail("credit")).toMatchObject({
      canonicalPath: "/macro/credit/cds",
      routeKind: "redirect",
      routeTail: "credit",
      wasUnknown: false,
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
      { label: "大类资产", href: "/macro/assets/equities" },
      { label: "加密衍生品", href: "/macro/assets/crypto-derivatives" },
    ]);
    expect(buildMacroBreadcrumbs("assets/correlation").map((crumb) => crumb.label)).toEqual([
      "宏观",
      "大类资产",
      "相关性",
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
      "/macro/assets/equities",
      "/macro/assets/correlation",
    ]);
  });
});
