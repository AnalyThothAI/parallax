export const MACRO_NAVIGATION_ITEMS = [
  { id: "overview", href: "/macro", label: "总览" },
  { id: "cross_asset", href: "/macro/cross-asset", label: "跨资产" },
  { id: "rates_inflation", href: "/macro/rates-inflation", label: "利率与通胀" },
  { id: "growth_labor", href: "/macro/growth-labor", label: "增长与就业" },
  { id: "liquidity_funding", href: "/macro/liquidity-funding", label: "流动性与资金" },
  { id: "credit", href: "/macro/credit", label: "信用" },
] as const;

export type MacroPageId = (typeof MACRO_NAVIGATION_ITEMS)[number]["id"];
