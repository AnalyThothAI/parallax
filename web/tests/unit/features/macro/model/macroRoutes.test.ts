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
      "rates/fed-funds",
      "rates/yield-curve",
      "rates/real-rates",
      "liquidity/rrp-tga",
      "economy/gdp",
      "economy/employment",
      "economy/inflation",
      "volatility/vix",
      "credit/stress",
    ]);
  });

  it("normalizes empty and nested module route tails while hard-deleting standalone correlation tails", () => {
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
    expect(parseMacroRouteTail("assets/correlation")).toBeNull();
    expect(parseMacroRouteTail("assets")).toMatchObject({
      canonicalPath: "/macro/assets",
      moduleId: "assets",
      pageKind: "leaf",
      productTier: "primary",
      routeKind: "module",
    });
    expect(parseMacroRouteTail("rates")).toBeNull();
    expect(parseMacroRouteTail("liquidity")).toBeNull();
    expect(parseMacroRouteTail("economy")).toBeNull();
    expect(parseMacroRouteTail("volatility")).toBeNull();
    expect(parseMacroRouteTail("credit")).toBeNull();
    expect(parseMacroRouteTail("fed")).toBeNull();
    expect(parseMacroRouteTail("rates/expectations")).toBeNull();
    expect(parseMacroRouteTail("liquidity/transmission-chain")).toBeNull();
    expect(parseMacroRouteTail("liquidity/operations")).toBeNull();
    expect(parseMacroRouteTail("liquidity/reserves")).toBeNull();
    expect(parseMacroRouteTail("liquidity/fed-balance-sheet")).toBeNull();
    expect(parseMacroRouteTail("not-real")).toBeNull();
  });

  it("builds canonical hrefs, labels, and breadcrumbs for nested modules", () => {
    expect(macroModuleHref("overview")).toBe("/macro");
    expect(macroModuleHref("assets")).toBe("/macro/assets");
    expect(macroModuleHref("assets/equities")).toBe("/macro/assets/equities");
    expect(macroRouteLabel("assets/equities")).toBe("美股");
    expect(macroModuleHref("liquidity/rrp-tga")).toBe("/macro/liquidity/rrp-tga");

    expect(buildMacroBreadcrumbs("assets/equities").map((crumb) => crumb.label)).toEqual([
      "宏观",
      "大类资产",
      "美股",
    ]);
  });

  it("derives navigation paths from the macro navigation tree", () => {
    expect(macroNavigationPath("assets").map((node) => node.label)).toEqual(["宏观", "大类资产"]);
    expect(macroNavigationPath("assets/equities").map((node) => node.label)).toEqual([
      "宏观",
      "大类资产",
      "美股",
    ]);
    expect(macroNavigationPath("assets").map((node) => node.href)).toEqual([
      "/macro",
      "/macro/assets",
    ]);
  });
});
