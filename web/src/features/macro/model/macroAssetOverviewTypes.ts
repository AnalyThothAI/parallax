export type AssetMarketGroup = {
  key: string;
  route: string;
  rows: AssetMarketRow[];
  title: string;
};

export type AssetMarketRow = {
  date: string;
  delta: string;
  deltaTone: "up" | "down" | "flat";
  id: string;
  latest: string;
  name: string;
  symbol: string;
};

export type MacroDailyBriefBlock = {
  body: string;
  id: string;
  stance: string;
  title: string;
};

export type MacroDailyBrief = {
  blocks: MacroDailyBriefBlock[];
  dataQuality?: MacroDailyBriefQuality;
  headline: string;
  status: string;
};

export type MacroDailyBriefQuality = {
  gapCount?: number;
  historyCoverageRatio?: number;
  latestCoverageRatio?: number;
  status: string;
};

export type AssetDiagnosticsSummary = {
  gapCount: number;
  moduleStatus: string;
  sourceCount: number;
};

export const ASSET_GROUPS: Array<{
  key: string;
  match: (rowKey: string) => boolean;
  route: string;
  title: string;
}> = [
  {
    key: "equities",
    match: (key) =>
      [
        "asset:spx",
        "asset:spy",
        "asset:qqq",
        "asset:ndx",
        "asset:dji",
        "asset:iwm",
        "asset:rut",
      ].includes(key),
    route: "/macro/assets/equities",
    title: "美股",
  },
  {
    key: "bonds",
    match: (key) =>
      key.startsWith("bond:") || ["asset:tlt", "asset:ief", "asset:hyg", "asset:lqd"].includes(key),
    route: "/macro/assets/bonds",
    title: "债券",
  },
  {
    key: "commodities",
    match: (key) => key.startsWith("commodity:"),
    route: "/macro/assets/commodities",
    title: "商品",
  },
  {
    key: "fx",
    match: (key) => key.startsWith("fx:"),
    route: "/macro/assets/fx",
    title: "外汇",
  },
  {
    key: "crypto",
    match: (key) => key.startsWith("crypto:"),
    route: "/macro/assets/crypto",
    title: "加密货币",
  },
];
