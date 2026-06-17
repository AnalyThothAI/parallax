import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "./macroNavigationTree";
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
  | "rates/fed-funds"
  | "rates/yield-curve"
  | "rates/real-rates"
  | "liquidity/rrp-tga"
  | "economy/gdp"
  | "economy/employment"
  | "economy/inflation"
  | "volatility/vix"
  | "credit/stress";

export type MacroRouteSection =
  | "overview"
  | "assets"
  | "rates"
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

export type MacroRouteResolution = {
  routeKind: "module";
  moduleId: MacroModuleId;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
  routeId: MacroModuleId;
  canonicalPath: string;
};

export type MacroBreadcrumb = {
  label: string;
  href: string;
};

export { MACRO_NAVIGATION_TREE, type MacroNavigationNode };

export const MACRO_MODULE_ROUTES: MacroModuleRoute[] =
  flattenMacroModuleRoutes(MACRO_NAVIGATION_TREE);

const ROUTES_BY_ID = new Map(MACRO_MODULE_ROUTES.map((route) => [route.moduleId, route]));

export function parseMacroRouteTail(routeTail: string | undefined): MacroRouteResolution | null {
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
    };
  }

  const descriptor = macroRouteDescriptor(normalized as MacroRouteId);
  if (descriptor) {
    return {
      canonicalPath: descriptor.href,
      moduleId: descriptor.routeId,
      pageKind: descriptor.pageKind,
      productTier: descriptor.productTier,
      routeId: descriptor.routeId,
      routeKind: "module",
    };
  }
  return null;
}

export function macroModuleHref(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.href ?? "/macro";
}

export function macroRouteLabel(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.label ?? "总览";
}

export function macroNavigationPath(routeId: MacroRouteId): MacroNavigationNode[] {
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
      node.routeId && node.section
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
