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
  | "rates/yield-curve"
  | "rates/real-rates"
  | "fed"
  | "liquidity"
  | "liquidity/transmission-chain"
  | "volatility"
  | "credit";

export type MacroRouteSection =
  | "overview"
  | "assets"
  | "rates"
  | "fed"
  | "liquidity"
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
      wasUnknown: boolean;
    }
  | {
      routeKind: "asset-correlation";
      canonicalPath: string;
      wasUnknown: false;
    };

export type MacroBreadcrumb = {
  label: string;
  href: string;
};

export const MACRO_MODULE_ROUTES: MacroModuleRoute[] = [
  { moduleId: "overview", label: "Overview", section: "overview", href: "/macro" },
  { moduleId: "assets", label: "Assets", section: "assets", href: "/macro/assets" },
  {
    moduleId: "assets/equities",
    label: "Equities",
    section: "assets",
    href: "/macro/assets/equities",
  },
  { moduleId: "assets/bonds", label: "Bonds", section: "assets", href: "/macro/assets/bonds" },
  {
    moduleId: "assets/commodities",
    label: "Commodities",
    section: "assets",
    href: "/macro/assets/commodities",
  },
  { moduleId: "assets/fx", label: "FX", section: "assets", href: "/macro/assets/fx" },
  { moduleId: "assets/crypto", label: "Crypto", section: "assets", href: "/macro/assets/crypto" },
  {
    moduleId: "assets/crypto-derivatives",
    label: "Crypto Derivatives",
    section: "assets",
    href: "/macro/assets/crypto-derivatives",
  },
  { moduleId: "rates", label: "Rates", section: "rates", href: "/macro/rates" },
  {
    moduleId: "rates/yield-curve",
    label: "Yield Curve",
    section: "rates",
    href: "/macro/rates/yield-curve",
  },
  {
    moduleId: "rates/real-rates",
    label: "Real Rates",
    section: "rates",
    href: "/macro/rates/real-rates",
  },
  { moduleId: "fed", label: "Fed", section: "fed", href: "/macro/fed" },
  { moduleId: "liquidity", label: "Liquidity", section: "liquidity", href: "/macro/liquidity" },
  {
    moduleId: "liquidity/transmission-chain",
    label: "Transmission Chain",
    section: "liquidity",
    href: "/macro/liquidity/transmission-chain",
  },
  {
    moduleId: "volatility",
    label: "Volatility",
    section: "volatility",
    href: "/macro/volatility",
  },
  { moduleId: "credit", label: "Credit", section: "credit", href: "/macro/credit" },
];

export const MACRO_ROUTE_GROUPS: Array<{ section: MacroRouteSection; label: string }> = [
  { section: "overview", label: "Overview" },
  { section: "assets", label: "Assets" },
  { section: "rates", label: "Rates" },
  { section: "fed", label: "Fed" },
  { section: "liquidity", label: "Liquidity" },
  { section: "volatility", label: "Volatility" },
  { section: "credit", label: "Credit" },
];

const ROUTES_BY_ID = new Map(MACRO_MODULE_ROUTES.map((route) => [route.moduleId, route]));

export function parseMacroRouteTail(routeTail: string | undefined): MacroRouteResolution {
  const normalized = normalizeRouteTail(routeTail);
  if (normalized === "assets/correlation") {
    return {
      canonicalPath: "/macro/assets/correlation",
      routeKind: "asset-correlation",
      wasUnknown: false,
    };
  }
  if (normalized === "") {
    return {
      canonicalPath: "/macro",
      moduleId: "overview",
      routeKind: "module",
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
    canonicalPath: "/macro",
    moduleId: "overview",
    routeKind: "module",
    wasUnknown: true,
  };
}

export function macroModuleHref(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.href ?? "/macro";
}

export function macroRouteLabel(moduleId: MacroModuleId): string {
  return ROUTES_BY_ID.get(moduleId)?.label ?? "Overview";
}

export function buildMacroBreadcrumbs(moduleId: MacroModuleId): MacroBreadcrumb[] {
  if (moduleId === "overview") {
    return [{ label: "Macro", href: "/macro" }];
  }
  const [section] = moduleId.split("/");
  const breadcrumbs: MacroBreadcrumb[] = [{ label: "Macro", href: "/macro" }];
  if (isMacroModuleId(section) && section !== moduleId) {
    breadcrumbs.push({ label: macroRouteLabel(section), href: macroModuleHref(section) });
  }
  breadcrumbs.push({ label: macroRouteLabel(moduleId), href: macroModuleHref(moduleId) });
  return breadcrumbs;
}

export function macroModuleRouteFromHref(href: string): MacroModuleRoute | undefined {
  return MACRO_MODULE_ROUTES.find((route) => route.href === href);
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
