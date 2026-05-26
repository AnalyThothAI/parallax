import {
  MACRO_NAVIGATION_TREE,
  type MacroNavigationNode,
} from "./macroNavigationTree";
import {
  macroRouteDescriptor,
  type MacroPageKind,
  type MacroProductTier,
  type MacroRouteId,
} from "./macroPageRegistry";

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
      pageKind: Exclude<MacroPageKind, "unsupported">;
      productTier: Exclude<MacroProductTier, "unsupported">;
      routeId: MacroModuleId;
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "matrix";
      pageKind: "matrix";
      productTier: Exclude<MacroProductTier, "unsupported">;
      routeId: "assets/correlation";
      canonicalPath: string;
      wasUnknown: false;
    }
  | {
      routeKind: "unsupported";
      pageKind: "unsupported";
      productTier: "unsupported";
      canonicalPath: string;
      routeTail: string;
      wasUnknown: true;
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
    const descriptor = macroRouteDescriptor("overview");
    return {
      canonicalPath: "/macro",
      moduleId: "overview",
      pageKind: descriptor?.pageKind ?? "overview",
      productTier: descriptor?.productTier ?? "primary",
      routeId: "overview",
      routeKind: "module",
      wasUnknown: false,
    };
  }

  const descriptor = macroRouteDescriptor(normalized as MacroRouteId);
  if (descriptor?.routeId === "assets/correlation") {
    return {
      canonicalPath: descriptor.href,
      pageKind: "matrix",
      productTier: descriptor.productTier,
      routeId: descriptor.routeId,
      routeKind: "matrix",
      wasUnknown: false,
    };
  }
  if (descriptor && isMacroModuleId(descriptor.routeId)) {
    return {
      canonicalPath: descriptor.href,
      moduleId: descriptor.routeId,
      pageKind: descriptor.pageKind,
      productTier: descriptor.productTier,
      routeId: descriptor.routeId,
      routeKind: "module",
      wasUnknown: false,
    };
  }
  return {
    canonicalPath: `/macro/${normalized}`,
    pageKind: "unsupported",
    productTier: "unsupported",
    routeKind: "unsupported",
    routeTail: normalized,
    wasUnknown: true,
  };
}

export function macroModuleHref(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.href ?? "/macro";
}

export function macroRouteLabel(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.label ?? "总览";
}

export function macroNavigationPath(
  routeId: MacroRouteId,
): MacroNavigationNode[] {
  return findNavigationPath(MACRO_NAVIGATION_TREE, routeId) ?? [];
}

export function buildMacroBreadcrumbs(routeId: MacroRouteId): MacroBreadcrumb[] {
  if (routeId === "overview") {
    return [{ label: "宏观", href: "/macro" }];
  }
  return macroNavigationPath(routeId).map((node) => ({
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
      node.routeId && node.routeId !== "assets/correlation" && node.section
        ? [
            {
              href: node.href,
              label: node.label,
              moduleId: node.routeId,
              section: node.section,
            },
          ]
        : [];
    return [...current, ...flattenMacroModuleRoutes(node.children ?? [])];
  });
}

function findNavigationPath(
  nodes: MacroNavigationNode[],
  routeId: MacroRouteId,
  ancestors: MacroNavigationNode[] = [],
): MacroNavigationNode[] | null {
  for (const node of nodes) {
    const path = [...ancestors, node];
    if (node.routeId === routeId) {
      return routeId === "overview" ? path.slice(0, 1) : path;
    }
    const childPath = findNavigationPath(node.children ?? [], routeId, path);
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

function isMacroModuleId(value: MacroRouteId): value is MacroModuleId {
  return value !== "assets/correlation";
}
