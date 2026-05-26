import {
  MACRO_NAVIGATION_TREE,
  type MacroNavigationNode,
} from "./macroNavigationTree";

export type MacroModuleId =
  | "overview"
  | "assets"
  | "assets/equities"
  | "assets/bonds"
  | "assets/commodities"
  | "assets/fx"
  | "assets/crypto"
  | "assets/crypto-derivatives"
  | "rates"
  | "rates/fed-funds"
  | "rates/yield-curve"
  | "rates/auctions"
  | "rates/real-rates"
  | "rates/expectations"
  | "fed"
  | "fed/statements"
  | "fed/speeches"
  | "liquidity"
  | "liquidity/transmission-chain"
  | "liquidity/fed-balance-sheet"
  | "liquidity/operations"
  | "liquidity/rrp-tga"
  | "liquidity/reserves"
  | "liquidity/global-dollar"
  | "liquidity/subsurface"
  | "economy"
  | "economy/gdp"
  | "economy/employment"
  | "economy/inflation"
  | "economy/consumer"
  | "volatility"
  | "volatility/dashboard"
  | "volatility/vix"
  | "credit"
  | "credit/cds"
  | "credit/stress";

export type MacroRouteSection =
  | "overview"
  | "assets"
  | "rates"
  | "fed"
  | "liquidity"
  | "economy"
  | "volatility"
  | "credit";

export type MacroModuleRoute = {
  moduleId: MacroModuleId;
  label: string;
  section: MacroRouteSection;
  href: string;
};

export type MacroRouteResolution =
  | {
      routeKind: "module";
      moduleId: MacroModuleId;
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "asset-correlation";
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "unsupported";
      canonicalPath: string;
      routeTail: string;
    };

export type MacroBreadcrumb = {
  label: string;
  href: string;
};

export { MACRO_NAVIGATION_TREE, type MacroNavigationNode };

export const MACRO_MODULE_ROUTES: MacroModuleRoute[] =
  flattenMacroModuleRoutes(MACRO_NAVIGATION_TREE);

const ROUTES_BY_ID = new Map(MACRO_MODULE_ROUTES.map((route) => [route.moduleId, route]));

export function parseMacroRouteTail(routeTail: string | undefined): MacroRouteResolution {
  const normalized = normalizeRouteTail(routeTail);
  if (normalized === "") {
    return {
      canonicalPath: "/macro",
      moduleId: "overview",
      routeKind: "module",
      wasUnknown: false,
    };
  }
  if (normalized === "assets/correlation") {
    return {
      canonicalPath: "/macro/assets/correlation",
      routeKind: "asset-correlation",
      wasUnknown: false,
    };
  }
  if (isMacroModuleId(normalized)) {
    return {
      canonicalPath: macroModuleHref(normalized),
      moduleId: normalized,
      routeKind: "module",
      wasUnknown: false,
    };
  }
  return {
    canonicalPath: `/macro/${normalized}`,
    routeKind: "unsupported",
    routeTail: normalized,
  };
}

export function macroModuleHref(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.href ?? "/macro";
}

export function macroRouteLabel(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.label ?? "总览";
}

export function macroNavigationPath(
  moduleId: MacroModuleId | "assets/correlation",
): MacroNavigationNode[] {
  return findNavigationPath(MACRO_NAVIGATION_TREE, moduleId) ?? [];
}

export function buildMacroBreadcrumbs(moduleId: MacroModuleId): MacroBreadcrumb[] {
  if (moduleId === "overview") {
    return [{ label: "宏观", href: "/macro" }];
  }
  return macroNavigationPath(moduleId).map((node) => ({
    label: node.label,
    href: node.href,
  }));
}

export function macroModuleRouteFromHref(href: string): MacroModuleRoute | undefined {
  return MACRO_MODULE_ROUTES.find((route) => route.href === href);
}

function flattenMacroModuleRoutes(nodes: MacroNavigationNode[]): MacroModuleRoute[] {
  return nodes.flatMap((node) => {
    const current =
      node.moduleId && node.moduleId !== "assets/correlation" && node.section
        ? [
            {
              href: node.href,
              label: node.label,
              moduleId: node.moduleId,
              section: node.section,
            },
          ]
        : [];
    return [...current, ...flattenMacroModuleRoutes(node.children ?? [])];
  });
}

function findNavigationPath(
  nodes: MacroNavigationNode[],
  moduleId: MacroModuleId | "assets/correlation",
  ancestors: MacroNavigationNode[] = [],
): MacroNavigationNode[] | null {
  for (const node of nodes) {
    const path = [...ancestors, node];
    if (node.moduleId === moduleId) {
      return moduleId === "overview" ? path.slice(0, 1) : path;
    }
    const childPath = findNavigationPath(node.children ?? [], moduleId, path);
    if (childPath) {
      return childPath;
    }
  }
  return null;
}

function normalizeRouteTail(routeTail: string | undefined): string {
  return (routeTail ?? "")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean)
    .join("/");
}

function isMacroModuleId(value: string): value is MacroModuleId {
  return ROUTES_BY_ID.has(value as MacroModuleId);
}
