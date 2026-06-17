import type { MacroPageKind, MacroProductTier, MacroRouteId } from "./macroPageRegistry";
import type { MacroRouteSection } from "./macroRoutes";

export type MacroNavigationNode = {
  label: string;
  href: string;
  matchPath?: string;
  pageKind?: MacroPageKind;
  productTier?: MacroProductTier;
  routeId?: MacroRouteId;
  section?: MacroRouteSection;
  children?: MacroNavigationNode[];
};

export const MACRO_NAVIGATION_TREE: MacroNavigationNode[] = [
  {
    label: "宏观",
    href: "/macro",
    children: [
      {
        label: "总览",
        href: "/macro",
        pageKind: "overview",
        productTier: "primary",
        routeId: "overview",
        section: "overview",
      },
      {
        label: "大类资产",
        href: "/macro/assets",
        matchPath: "/macro/assets/*",
        pageKind: "leaf",
        productTier: "primary",
        routeId: "assets",
        section: "assets",
        children: [
          {
            label: "美股",
            href: "/macro/assets/equities",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "assets/equities",
            section: "assets",
          },
          {
            label: "债券",
            href: "/macro/assets/bonds",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "assets/bonds",
            section: "assets",
          },
          {
            label: "商品",
            href: "/macro/assets/commodities",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "assets/commodities",
            section: "assets",
          },
          {
            label: "外汇",
            href: "/macro/assets/fx",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "assets/fx",
            section: "assets",
          },
          {
            label: "加密资产",
            href: "/macro/assets/crypto",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "assets/crypto",
            section: "assets",
          },
        ],
      },
      {
        label: "利率",
        href: "/macro/rates/fed-funds",
        matchPath: "/macro/rates/*",
        section: "rates",
        children: [
          {
            label: "联邦基金",
            href: "/macro/rates/fed-funds",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "rates/fed-funds",
            section: "rates",
          },
          {
            label: "收益率曲线",
            href: "/macro/rates/yield-curve",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "rates/yield-curve",
            section: "rates",
          },
          {
            label: "实际利率",
            href: "/macro/rates/real-rates",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "rates/real-rates",
            section: "rates",
          },
        ],
      },
      {
        label: "流动性",
        href: "/macro/liquidity/rrp-tga",
        matchPath: "/macro/liquidity/*",
        section: "liquidity",
        children: [
          {
            label: "RRP / TGA",
            href: "/macro/liquidity/rrp-tga",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/rrp-tga",
            section: "liquidity",
          },
        ],
      },
      {
        label: "经济数据",
        href: "/macro/economy/gdp",
        matchPath: "/macro/economy/*",
        section: "economy",
        children: [
          {
            label: "GDP",
            href: "/macro/economy/gdp",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "economy/gdp",
            section: "economy",
          },
          {
            label: "就业",
            href: "/macro/economy/employment",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "economy/employment",
            section: "economy",
          },
          {
            label: "通胀",
            href: "/macro/economy/inflation",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "economy/inflation",
            section: "economy",
          },
        ],
      },
      {
        label: "波动率",
        href: "/macro/volatility/vix",
        matchPath: "/macro/volatility/*",
        section: "volatility",
        children: [
          {
            label: "VIX",
            href: "/macro/volatility/vix",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "volatility/vix",
            section: "volatility",
          },
        ],
      },
      {
        label: "信用",
        href: "/macro/credit/stress",
        matchPath: "/macro/credit/*",
        section: "credit",
        children: [
          {
            label: "压力",
            href: "/macro/credit/stress",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "credit/stress",
            section: "credit",
          },
        ],
      },
    ],
  },
];
