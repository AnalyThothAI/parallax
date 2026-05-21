import type { components } from "./openapi";

export type { components, operations, paths } from "./openapi";

export type OpenApiBootstrapData = components["schemas"]["BootstrapData"];
export type OpenApiStatusData = components["schemas"]["StatusData"];
export type OpenApiRecentData = components["schemas"]["RecentData"];
export type OpenApiSearchData = components["schemas"]["SearchData"];
export type OpenApiSearchInspectData = components["schemas"]["SearchInspectData"];
export type OpenApiTokenRadarData = components["schemas"]["TokenRadarData"];
export type OpenApiStocksRadarData = components["schemas"]["StocksRadarData"];
export type OpenApiLiveMarketData = components["schemas"]["LiveMarketData"];
export type OpenApiTargetPostsData = components["schemas"]["TargetPostsData"];
export type OpenApiTargetSocialTimelineData = components["schemas"]["TargetSocialTimelineData"];
export type OpenApiAccountAlertsData = components["schemas"]["AccountAlertsData"];
export type OpenApiAccountQualityData = components["schemas"]["AccountQualityData"];
export type OpenApiNotificationSummary = components["schemas"]["NotificationSummary"];
export type OpenApiNotificationsData = components["schemas"]["NotificationsData"];
export type OpenApiNotificationReadData = components["schemas"]["NotificationReadData"];
export type OpenApiNotificationReadAllData = components["schemas"]["NotificationReadAllData"];
export type OpenApiSignalPulseData = components["schemas"]["SignalPulseData"];
export type OpenApiSignalPulseItem = components["schemas"]["SignalPulseItem"];

// frontend-contracts: these UI/domain shapes still encode frontend-specific view models
// that are richer than the current extensible OpenAPI response schemas.
export type {
  AccountQualityData,
  AlertRecord,
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  BootstrapData,
  CexDetailSnapshot,
  CexLevelBand,
  Decision,
  EntityRecord,
  EventRecord,
  EvidenceRef,
  FactorPoint,
  LiveMarketUpdatePayload,
  LivePayload,
  LiveMarketSnapshot,
  MacroIndicator,
  MacroPanel,
  MacroTrigger,
  MacroViewsData,
  MacroViewSnapshotSummary,
  MarketCandle,
  MarketContext,
  MarketObservationSnapshot,
  NarrativeArgument,
  NarrativeCluster,
  NarrativeCurrentness,
  NarrativeCurrentnessDisplayStatus,
  NarrativeStatus,
  NotificationItem,
  NotificationLivePayload,
  NotificationSummary,
  NotificationsData,
  PulseOverlay,
  RadarSortMode,
  RecentData,
  ScopeKey,
  SearchAgentBrief,
  SearchAmbiguousResult,
  SearchData,
  SearchInspectData,
  SearchItem,
  SearchTargetCandidate,
  SearchTopicResult,
  SearchTokenResult,
  ScoreBlock,
  ScoreContribution,
  SignalPulseData,
  SignalPulseItem,
  SignalPulseStageName,
  SignalPulseStagePayload,
  SignalPulseStages,
  SignalPulseStatus,
  SignalPulseStatusFilter,
  SignalPulseVisibilityFilter,
  SocialEventDetail,
  SocialEventsByIdsData,
  StatusData,
  StockRadarRow,
  StocksRadarData,
  TimelineBucket,
  TimingBlock,
  TokenDetailMode,
  TokenDetailTab,
  TokenCaseDossier,
  TokenCaseApiScope,
  TokenCasePostsData,
  TokenCasePostsQuery,
  TokenCaseSocialTimelineData,
  TokenCaseSocialTimelineQuery,
  TokenDiscussionDigest,
  TokenFactorFamily,
  TokenFactorFamilyKey,
  TokenFactorSnapshot,
  TokenFlowItem,
  TokenIntentRecord,
  TokenMarketBlock,
  TokenMentionSemantic,
  TokenPostItem,
  TokenPostRange,
  TokenPostServerSort,
  TokenPostSortMode,
  TokenPostsData,
  TokenProfileBlock,
  TokenRadarRowMeta,
  TokenReference,
  TokenResolutionRecord,
  TokenSocialTimelineData,
  TokenTimelineStage,
  TokenTimelinePost,
  TradeabilityBlock,
  WatchlistHandleSummaryData,
  WatchlistHandleOverviewData,
  WatchlistHandleRowOverview,
  WatchlistHandlesOverviewData,
  WatchlistOverviewCluster,
  WatchlistHandleTimelineData,
  WatchlistSocialEvent,
  WatchlistTimelineItem,
  WatchlistTimelineScope,
  WatchlistTopic,
  WindowKey,
} from "./frontend-contracts";
