export type TokenCaseScope = "all" | "watched";
export type TokenCaseSort = "catalyst" | "recent" | "watched";
export type TokenCaseWindow = "5m" | "1h" | "4h" | "24h";
export type TokenCaseTone =
  | "neutral"
  | "health"
  | "info"
  | "warn"
  | "risk"
  | "agent"
  | "opportunity";

export type TokenCaseMetric = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: TokenCaseTone;
};

export type TokenCasePostEvent = {
  id: string;
  handle: string | null;
  text: string;
  sourceText?: string | null;
  detailsLabel?: string | null;
  url: string | null;
  timestampMs: number | null;
  timeLabel: string | null;
  phase: string | null;
  role: string | null;
  isWatched: boolean;
  pills: Array<{ label: string; tone: TokenCaseTone }>;
  market: {
    eventPriceLabel: string;
    liveDeltaLabel: string | null;
    providerLabel: string;
    tone: TokenCaseTone;
  } | null;
  quality: {
    score: number | null;
    scoreLabel: string;
    reasons: string[];
    contributions: Array<{ label: string; value: string; reason: string }>;
  };
};

export type TokenCaseMarketView = {
  status: string;
  provider: string | null;
  priceLabel: string;
  marketCapLabel: string;
  liquidityLabel: string;
  holdersLabel: string;
  volume24hLabel: string;
  openInterestLabel: string;
  observedAtLabel: string | null;
  emptyTitle: string | null;
  emptyDetail: string | null;
  tone: TokenCaseTone;
};

export type TokenCaseThesisView = {
  title: string;
  thesis: string;
  evidenceEventIds: string[];
  bullets: string[];
  tone: TokenCaseTone;
};

export type TokenCaseNarrativeCurrentnessView = {
  displayStatus: string;
  reason: string | null;
  label: string;
  tone: TokenCaseTone;
  lastReadyComputedAtMs: number | null;
  lastReadyComputedLabel: string | null;
  deltaSourceEventCount: number;
  deltaIndependentAuthorCount: number;
  deltaLabel: string | null;
};

export type TokenCaseViewModel = {
  target: {
    targetType: "Asset" | "CexToken" | string;
    targetId: string;
    symbol: string | null;
    name: string | null;
    chainId: string | null;
    address: string | null;
    displayTitle: string;
    shortId: string;
  };
  route: {
    window: TokenCaseWindow;
    scope: TokenCaseScope;
    searchHref: string;
  };
  hero: {
    logoUrl: string | null;
    title: string;
    subtitle: string;
    contractLabel: string | null;
    actions: Array<{ label: string; href: string; tone: TokenCaseTone }>;
  };
  metrics: TokenCaseMetric[];
  propagation: {
    summaryZh: string;
    currentness: TokenCaseNarrativeCurrentnessView;
    statusPills: Array<{ label: string; tone: TokenCaseTone }>;
    stages: Array<{
      id: string;
      phase: string;
      count: number;
      authors: number;
      leadAccount: string | null;
      readZh: string;
      tone: TokenCaseTone;
    }>;
  };
  timeline: {
    sort: TokenCaseSort;
    items: TokenCasePostEvent[];
    hasMore: boolean;
    isLoading: boolean;
    isFetchingNextPage: boolean;
    emptyLabel: string | null;
  };
  market: TokenCaseMarketView;
  bullBear: {
    stance: string;
    bull: TokenCaseThesisView;
    bear: TokenCaseThesisView;
  };
  amplifiers: Array<{
    handle: string;
    role: string;
    posts: number;
    firstSeenLabel: string | null;
  }>;
  dataGaps: string[];
};
