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

export type MacroNavigationRoute = {
  href: string;
  label: string;
  moduleId: MacroModuleId | "assets/correlation";
  section: MacroRouteSection;
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
  { moduleId: "overview", label: "总览", section: "overview", href: "/macro" },
  { moduleId: "assets", label: "大类资产", section: "assets", href: "/macro/assets" },
  {
    moduleId: "assets/equities",
    label: "美股",
    section: "assets",
    href: "/macro/assets/equities",
  },
  { moduleId: "assets/bonds", label: "债券", section: "assets", href: "/macro/assets/bonds" },
  {
    moduleId: "assets/commodities",
    label: "商品",
    section: "assets",
    href: "/macro/assets/commodities",
  },
  { moduleId: "assets/fx", label: "外汇", section: "assets", href: "/macro/assets/fx" },
  { moduleId: "assets/crypto", label: "加密资产", section: "assets", href: "/macro/assets/crypto" },
  {
    moduleId: "assets/crypto-derivatives",
    label: "加密衍生品",
    section: "assets",
    href: "/macro/assets/crypto-derivatives",
  },
  { moduleId: "rates", label: "利率", section: "rates", href: "/macro/rates" },
  {
    moduleId: "rates/fed-funds",
    label: "联邦基金",
    section: "rates",
    href: "/macro/rates/fed-funds",
  },
  {
    moduleId: "rates/yield-curve",
    label: "收益率曲线",
    section: "rates",
    href: "/macro/rates/yield-curve",
  },
  {
    moduleId: "rates/auctions",
    label: "拍卖",
    section: "rates",
    href: "/macro/rates/auctions",
  },
  {
    moduleId: "rates/real-rates",
    label: "实际利率",
    section: "rates",
    href: "/macro/rates/real-rates",
  },
  {
    moduleId: "rates/expectations",
    label: "政策预期",
    section: "rates",
    href: "/macro/rates/expectations",
  },
  { moduleId: "fed", label: "美联储", section: "fed", href: "/macro/fed" },
  {
    moduleId: "fed/statements",
    label: "FOMC 声明",
    section: "fed",
    href: "/macro/fed/statements",
  },
  {
    moduleId: "fed/speeches",
    label: "讲话",
    section: "fed",
    href: "/macro/fed/speeches",
  },
  { moduleId: "liquidity", label: "流动性", section: "liquidity", href: "/macro/liquidity" },
  {
    moduleId: "liquidity/transmission-chain",
    label: "传导链",
    section: "liquidity",
    href: "/macro/liquidity/transmission-chain",
  },
  {
    moduleId: "liquidity/fed-balance-sheet",
    label: "资产负债表",
    section: "liquidity",
    href: "/macro/liquidity/fed-balance-sheet",
  },
  {
    moduleId: "liquidity/operations",
    label: "公开市场操作",
    section: "liquidity",
    href: "/macro/liquidity/operations",
  },
  {
    moduleId: "liquidity/rrp-tga",
    label: "RRP/TGA",
    section: "liquidity",
    href: "/macro/liquidity/rrp-tga",
  },
  {
    moduleId: "liquidity/reserves",
    label: "准备金",
    section: "liquidity",
    href: "/macro/liquidity/reserves",
  },
  {
    moduleId: "liquidity/global-dollar",
    label: "全球美元",
    section: "liquidity",
    href: "/macro/liquidity/global-dollar",
  },
  {
    moduleId: "liquidity/subsurface",
    label: "暗流",
    section: "liquidity",
    href: "/macro/liquidity/subsurface",
  },
  { moduleId: "economy", label: "经济", section: "economy", href: "/macro/economy" },
  { moduleId: "economy/gdp", label: "GDP", section: "economy", href: "/macro/economy/gdp" },
  {
    moduleId: "economy/employment",
    label: "就业",
    section: "economy",
    href: "/macro/economy/employment",
  },
  {
    moduleId: "economy/inflation",
    label: "通胀",
    section: "economy",
    href: "/macro/economy/inflation",
  },
  {
    moduleId: "economy/consumer",
    label: "消费",
    section: "economy",
    href: "/macro/economy/consumer",
  },
  {
    moduleId: "volatility",
    label: "波动率",
    section: "volatility",
    href: "/macro/volatility",
  },
  {
    moduleId: "volatility/dashboard",
    label: "Dashboard",
    section: "volatility",
    href: "/macro/volatility/dashboard",
  },
  {
    moduleId: "volatility/vix",
    label: "VIX",
    section: "volatility",
    href: "/macro/volatility/vix",
  },
  { moduleId: "credit", label: "信用", section: "credit", href: "/macro/credit" },
  { moduleId: "credit/cds", label: "CDS 代理", section: "credit", href: "/macro/credit/cds" },
  { moduleId: "credit/stress", label: "压力", section: "credit", href: "/macro/credit/stress" },
];

const ROUTES_BY_ID = new Map(MACRO_MODULE_ROUTES.map((route) => [route.moduleId, route]));

const PRIMARY_ROUTE_IDS: MacroModuleId[] = [
  "overview",
  "assets",
  "rates",
  "fed",
  "liquidity",
  "economy",
  "volatility",
  "credit",
];

const ASSET_CORRELATION_ROUTE: MacroNavigationRoute = {
  href: "/macro/assets/correlation",
  label: "相关性",
  moduleId: "assets/correlation",
  section: "assets",
};

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
  return ROUTES_BY_ID.get(moduleId)?.label ?? "总览";
}

export function macroActiveSection(
  moduleId: MacroModuleId | "assets/correlation",
): MacroRouteSection {
  if (moduleId === "overview") {
    return "overview";
  }
  return moduleId.split("/")[0] as MacroRouteSection;
}

export function macroPrimaryTabRoutes(): MacroModuleRoute[] {
  return PRIMARY_ROUTE_IDS.map((moduleId) => ROUTES_BY_ID.get(moduleId)).filter(
    (route): route is MacroModuleRoute => Boolean(route),
  );
}

export function macroSecondaryTabRoutes(section: MacroRouteSection): MacroNavigationRoute[] {
  if (section === "overview") {
    return [];
  }
  const routes = MACRO_MODULE_ROUTES.filter((route) => route.section === section).map(
    (route): MacroNavigationRoute => route,
  );
  if (section === "assets") {
    return [...routes, ASSET_CORRELATION_ROUTE];
  }
  return routes.length > 1 ? routes : [];
}

export function buildMacroBreadcrumbs(moduleId: MacroModuleId): MacroBreadcrumb[] {
  if (moduleId === "overview") {
    return [{ label: "宏观", href: "/macro" }];
  }
  const [section] = moduleId.split("/");
  const breadcrumbs: MacroBreadcrumb[] = [{ label: "宏观", href: "/macro" }];
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
