import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "./macroNavigationTree";
import type { MacroModuleId } from "./macroRoutes";

export type MacroPageKind = "overview" | "leaf";
export type MacroProductTier = "primary";
export type MacroRouteId = MacroModuleId;
export type MacroRouteDescriptor = {
  href: string;
  label: string;
  pageKind: MacroPageKind;
  productTier: MacroProductTier;
  routeId: MacroRouteId;
};

export const MACRO_ROUTE_DESCRIPTORS: MacroRouteDescriptor[] =
  flattenMacroRouteDescriptors(MACRO_NAVIGATION_TREE);

export const supportedMacroAuditRoutes = MACRO_ROUTE_DESCRIPTORS;

const ROUTE_DESCRIPTORS_BY_ID = new Map(
  MACRO_ROUTE_DESCRIPTORS.map((route) => [route.routeId, route]),
);

export function macroRouteDescriptor(routeId: MacroRouteId): MacroRouteDescriptor | undefined {
  return ROUTE_DESCRIPTORS_BY_ID.get(routeId);
}

export function flattenMacroRouteDescriptors(nodes: MacroNavigationNode[]): MacroRouteDescriptor[] {
  return nodes.flatMap((node) => {
    const hasRouteMetadata = Boolean(node.routeId || node.pageKind || node.productTier);
    if (hasRouteMetadata && (!node.routeId || !node.pageKind || !node.productTier)) {
      throw new Error(
        `Macro route node is partially annotated: ${node.href} (${node.label}) requires routeId, pageKind, and productTier.`,
      );
    }

    const current =
      node.routeId && node.pageKind && node.productTier
        ? [
            {
              href: node.href,
              label: node.label,
              pageKind: node.pageKind,
              productTier: node.productTier,
              routeId: node.routeId,
            },
          ]
        : [];

    return [...current, ...flattenMacroRouteDescriptors(node.children ?? [])];
  });
}
