import {
  MACRO_MODULE_ROUTES,
  buildMacroBreadcrumbs,
  macroActiveSection,
  macroModuleHref,
  macroPrimaryTabRoutes,
  macroSecondaryTabRoutes,
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
      "rates/yield-curve",
      "rates/real-rates",
      "fed",
      "liquidity",
      "liquidity/transmission-chain",
      "volatility",
      "credit",
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
    expect(parseMacroRouteTail("assets/unknown")).toMatchObject({
      canonicalPath: "/macro",
      moduleId: "overview",
      routeKind: "module",
      wasUnknown: true,
    });
  });

  it("builds canonical hrefs and breadcrumbs for nested modules", () => {
    expect(macroModuleHref("overview")).toBe("/macro");
    expect(macroModuleHref("liquidity/transmission-chain")).toBe(
      "/macro/liquidity/transmission-chain",
    );

    expect(buildMacroBreadcrumbs("assets/crypto-derivatives")).toEqual([
      { label: "宏观", href: "/macro" },
      { label: "大类资产", href: "/macro/assets" },
      { label: "加密衍生品", href: "/macro/assets/crypto-derivatives" },
    ]);
  });

  it("groups macro routes into primary and secondary tabs", () => {
    expect(macroPrimaryTabRoutes().map((route) => route.moduleId)).toEqual([
      "overview",
      "assets",
      "rates",
      "fed",
      "liquidity",
      "volatility",
      "credit",
    ]);
    expect(macroSecondaryTabRoutes("assets").map((route) => route.href)).toEqual([
      "/macro/assets",
      "/macro/assets/equities",
      "/macro/assets/bonds",
      "/macro/assets/commodities",
      "/macro/assets/fx",
      "/macro/assets/crypto",
      "/macro/assets/crypto-derivatives",
      "/macro/assets/correlation",
    ]);
    expect(macroSecondaryTabRoutes("rates").map((route) => route.href)).toEqual([
      "/macro/rates",
      "/macro/rates/yield-curve",
      "/macro/rates/real-rates",
    ]);
    expect(macroSecondaryTabRoutes("overview")).toEqual([]);
    expect(macroActiveSection("assets/crypto")).toBe("assets");
    expect(macroActiveSection("liquidity/transmission-chain")).toBe("liquidity");
    expect(macroActiveSection("fed")).toBe("fed");
  });
});
