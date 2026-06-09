import type { MacroPageKind, MacroProductTier, MacroRouteId } from "./macroPageRegistry";
import type { MacroRouteSection } from "./macroRoutes";

type SupportedMacroPageKind = Exclude<MacroPageKind, "unsupported">;
type SupportedMacroProductTier = Exclude<MacroProductTier, "unsupported">;

export type MacroNavigationNode = {
  label: string;
  href: string;
  matchPath?: string;
  navHidden?: boolean;
  pageKind?: SupportedMacroPageKind;
  productTier?: SupportedMacroProductTier;
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
          {
            label: "加密衍生品",
            href: "/macro/assets/crypto-derivatives",
            pageKind: "leaf",
            productTier: "secondary",
            routeId: "assets/crypto-derivatives",
            section: "assets",
          },
          {
            label: "相关性",
            href: "/macro/assets/correlation",
            pageKind: "matrix",
            productTier: "primary",
            routeId: "assets/correlation",
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
            label: "拍卖",
            href: "/macro/rates/auctions",
            navHidden: true,
            pageKind: "leaf",
            productTier: "hiddenSupported",
            routeId: "rates/auctions",
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
          {
            label: "政策预期",
            href: "/macro/rates/expectations",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "rates/expectations",
            section: "rates",
          },
        ],
      },
      {
        label: "美联储",
        href: "/macro/fed/statements",
        matchPath: "/macro/fed/*",
        section: "fed",
        children: [
          {
            label: "FOMC 声明",
            href: "/macro/fed/statements",
            navHidden: true,
            pageKind: "leaf",
            productTier: "hiddenSupported",
            routeId: "fed/statements",
            section: "fed",
          },
          {
            label: "美联储讲话",
            href: "/macro/fed/speeches",
            navHidden: true,
            pageKind: "leaf",
            productTier: "hiddenSupported",
            routeId: "fed/speeches",
            section: "fed",
          },
        ],
      },
      {
        label: "流动性",
        href: "/macro/liquidity/transmission-chain",
        matchPath: "/macro/liquidity/*",
        section: "liquidity",
        children: [
          {
            label: "传导链",
            href: "/macro/liquidity/transmission-chain",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/transmission-chain",
            section: "liquidity",
          },
          {
            label: "资产负债表",
            href: "/macro/liquidity/fed-balance-sheet",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/fed-balance-sheet",
            section: "liquidity",
          },
          {
            label: "公开市场操作",
            href: "/macro/liquidity/operations",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/operations",
            section: "liquidity",
          },
          {
            label: "RRP / TGA",
            href: "/macro/liquidity/rrp-tga",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/rrp-tga",
            section: "liquidity",
          },
          {
            label: "银行准备金",
            href: "/macro/liquidity/reserves",
            pageKind: "leaf",
            productTier: "primary",
            routeId: "liquidity/reserves",
            section: "liquidity",
          },
          {
            label: "全球美元",
            href: "/macro/liquidity/global-dollar",
            pageKind: "leaf",
            productTier: "secondary",
            routeId: "liquidity/global-dollar",
            section: "liquidity",
          },
          {
            label: "资金面暗流",
            href: "/macro/liquidity/subsurface",
            pageKind: "leaf",
            productTier: "secondary",
            routeId: "liquidity/subsurface",
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
          {
            label: "消费",
            href: "/macro/economy/consumer",
            pageKind: "leaf",
            productTier: "secondary",
            routeId: "economy/consumer",
            section: "economy",
          },
        ],
      },
      {
        label: "波动率",
        href: "/macro/volatility/dashboard",
        matchPath: "/macro/volatility/*",
        section: "volatility",
        children: [
          {
            label: "Dashboard",
            href: "/macro/volatility/dashboard",
            navHidden: true,
            pageKind: "leaf",
            productTier: "hiddenSupported",
            routeId: "volatility/dashboard",
            section: "volatility",
          },
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
        href: "/macro/credit/cds",
        matchPath: "/macro/credit/*",
        section: "credit",
        children: [
          {
            label: "CDS 代理",
            href: "/macro/credit/cds",
            navHidden: true,
            pageKind: "leaf",
            productTier: "hiddenSupported",
            routeId: "credit/cds",
            section: "credit",
          },
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
