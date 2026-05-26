import type { MacroModuleId, MacroRouteSection } from "./macroRoutes";

export type MacroNavigationNode = {
  label: string;
  href: string;
  moduleId?: MacroModuleId | "assets/correlation";
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
        moduleId: "overview",
        section: "overview",
      },
      {
        label: "大类资产",
        href: "/macro/assets",
        moduleId: "assets",
        section: "assets",
        children: [
          {
            label: "美股",
            href: "/macro/assets/equities",
            moduleId: "assets/equities",
            section: "assets",
          },
          {
            label: "债券",
            href: "/macro/assets/bonds",
            moduleId: "assets/bonds",
            section: "assets",
          },
          {
            label: "商品",
            href: "/macro/assets/commodities",
            moduleId: "assets/commodities",
            section: "assets",
          },
          {
            label: "外汇",
            href: "/macro/assets/fx",
            moduleId: "assets/fx",
            section: "assets",
          },
          {
            label: "加密资产",
            href: "/macro/assets/crypto",
            moduleId: "assets/crypto",
            section: "assets",
          },
          {
            label: "加密衍生品",
            href: "/macro/assets/crypto-derivatives",
            moduleId: "assets/crypto-derivatives",
            section: "assets",
          },
          {
            label: "相关性",
            href: "/macro/assets/correlation",
            moduleId: "assets/correlation",
            section: "assets",
          },
        ],
      },
      {
        label: "利率",
        href: "/macro/rates",
        moduleId: "rates",
        section: "rates",
        children: [
          {
            label: "联邦基金",
            href: "/macro/rates/fed-funds",
            moduleId: "rates/fed-funds",
            section: "rates",
          },
          {
            label: "收益率曲线",
            href: "/macro/rates/yield-curve",
            moduleId: "rates/yield-curve",
            section: "rates",
          },
          {
            label: "拍卖",
            href: "/macro/rates/auctions",
            moduleId: "rates/auctions",
            section: "rates",
          },
          {
            label: "实际利率",
            href: "/macro/rates/real-rates",
            moduleId: "rates/real-rates",
            section: "rates",
          },
          {
            label: "政策预期",
            href: "/macro/rates/expectations",
            moduleId: "rates/expectations",
            section: "rates",
          },
        ],
      },
      {
        label: "美联储",
        href: "/macro/fed",
        moduleId: "fed",
        section: "fed",
        children: [
          {
            label: "FOMC 声明",
            href: "/macro/fed/statements",
            moduleId: "fed/statements",
            section: "fed",
          },
          {
            label: "美联储讲话",
            href: "/macro/fed/speeches",
            moduleId: "fed/speeches",
            section: "fed",
          },
        ],
      },
      {
        label: "流动性",
        href: "/macro/liquidity",
        moduleId: "liquidity",
        section: "liquidity",
        children: [
          {
            label: "传导链",
            href: "/macro/liquidity/transmission-chain",
            moduleId: "liquidity/transmission-chain",
            section: "liquidity",
          },
          {
            label: "资产负债表",
            href: "/macro/liquidity/fed-balance-sheet",
            moduleId: "liquidity/fed-balance-sheet",
            section: "liquidity",
          },
          {
            label: "公开市场操作",
            href: "/macro/liquidity/operations",
            moduleId: "liquidity/operations",
            section: "liquidity",
          },
          {
            label: "RRP / TGA",
            href: "/macro/liquidity/rrp-tga",
            moduleId: "liquidity/rrp-tga",
            section: "liquidity",
          },
          {
            label: "银行准备金",
            href: "/macro/liquidity/reserves",
            moduleId: "liquidity/reserves",
            section: "liquidity",
          },
          {
            label: "全球美元",
            href: "/macro/liquidity/global-dollar",
            moduleId: "liquidity/global-dollar",
            section: "liquidity",
          },
          {
            label: "资金面暗流",
            href: "/macro/liquidity/subsurface",
            moduleId: "liquidity/subsurface",
            section: "liquidity",
          },
        ],
      },
      {
        label: "经济数据",
        href: "/macro/economy",
        moduleId: "economy",
        section: "economy",
        children: [
          {
            label: "GDP",
            href: "/macro/economy/gdp",
            moduleId: "economy/gdp",
            section: "economy",
          },
          {
            label: "就业",
            href: "/macro/economy/employment",
            moduleId: "economy/employment",
            section: "economy",
          },
          {
            label: "通胀",
            href: "/macro/economy/inflation",
            moduleId: "economy/inflation",
            section: "economy",
          },
          {
            label: "消费",
            href: "/macro/economy/consumer",
            moduleId: "economy/consumer",
            section: "economy",
          },
        ],
      },
      {
        label: "波动率",
        href: "/macro/volatility",
        moduleId: "volatility",
        section: "volatility",
        children: [
          {
            label: "Dashboard",
            href: "/macro/volatility/dashboard",
            moduleId: "volatility/dashboard",
            section: "volatility",
          },
          {
            label: "VIX",
            href: "/macro/volatility/vix",
            moduleId: "volatility/vix",
            section: "volatility",
          },
        ],
      },
      {
        label: "信用",
        href: "/macro/credit",
        moduleId: "credit",
        section: "credit",
        children: [
          {
            label: "CDS 代理",
            href: "/macro/credit/cds",
            moduleId: "credit/cds",
            section: "credit",
          },
          {
            label: "压力",
            href: "/macro/credit/stress",
            moduleId: "credit/stress",
            section: "credit",
          },
        ],
      },
    ],
  },
];
