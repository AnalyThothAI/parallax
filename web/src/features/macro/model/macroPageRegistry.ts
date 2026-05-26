import { MACRO_NAVIGATION_TREE, type MacroNavigationNode } from "./macroNavigationTree";
import type { MacroModuleId } from "./macroRoutes";

export type MacroPageKind = "overview" | "index" | "leaf" | "matrix" | "unsupported";
export type MacroProductTier = "primary" | "secondary" | "hiddenSupported" | "unsupported";
export type MacroRouteId = MacroModuleId | "assets/correlation";
export type MacroRouteDescriptor = {
  href: string;
  label: string;
  pageKind: Exclude<MacroPageKind, "unsupported">;
  productTier: Exclude<MacroProductTier, "unsupported">;
  routeId: MacroRouteId;
};

export const HIDDEN_MACRO_NAV_LABELS = [
  "拍卖",
  "FOMC 声明",
  "美联储讲话",
  "Dashboard",
  "CDS 代理",
] as const;

export const MACRO_ROUTE_DESCRIPTORS: MacroRouteDescriptor[] =
  flattenMacroRouteDescriptors(MACRO_NAVIGATION_TREE);

export const supportedMacroAuditRoutes = MACRO_ROUTE_DESCRIPTORS.filter(
  (route) => route.productTier !== "hiddenSupported",
);

export const hiddenMacroDirectRoutes = MACRO_ROUTE_DESCRIPTORS.filter(
  (route) => route.productTier === "hiddenSupported",
);

const ROUTE_DESCRIPTORS_BY_ID = new Map(
  MACRO_ROUTE_DESCRIPTORS.map((route) => [route.routeId, route]),
);

export function macroRouteDescriptor(routeId: MacroRouteId): MacroRouteDescriptor | undefined {
  return ROUTE_DESCRIPTORS_BY_ID.get(routeId);
}

export function flattenMacroRouteDescriptors(
  nodes: MacroNavigationNode[],
): MacroRouteDescriptor[] {
  return nodes.flatMap((node) => {
    const hasRouteMetadata = Boolean(node.routeId || node.pageKind || node.productTier);
    if (hasRouteMetadata && (!node.routeId || !node.pageKind || !node.productTier)) {
      throw new Error(
        `Macro route node is partially annotated: ${node.href} (${node.label}) requires routeId, pageKind, and productTier.`,
      );
    }

    const current = hasRouteMetadata
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
