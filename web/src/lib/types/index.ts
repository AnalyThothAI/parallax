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
export type OpenApiNotificationSummary = components["schemas"]["NotificationSummary"];
export type OpenApiNotificationsData = components["schemas"]["NotificationsData"];
export type OpenApiNotificationReadData = components["schemas"]["NotificationReadData"];
export type OpenApiNotificationReadAllData = components["schemas"]["NotificationReadAllData"];

// frontend-contracts: these UI/domain shapes still encode frontend-specific view models
// that are richer than the current extensible OpenAPI response schemas.
export type {
  AlertRecord,
  ApiResponse,
  AssetFlowData,
  AssetFlowRow,
  BootstrapData,
  Decision,
  EntityRecord,
  EventRecord,
  FactorPoint,
  LiveMarketUpdatePayload,
  LivePayload,
  LiveMarketSnapshot,
  MarketCandle,
  MarketContext,
  MarketObservationSnapshot,
  NotificationItem,
  NotificationLivePayload,
  NotificationSummary,
  NotificationsData,
  RadarSortMode,
  RecentData,
  ScopeKey,
  SearchAmbiguousResult,
  SearchData,
  SearchInspectData,
  SearchItem,
  SearchTargetCandidate,
  SearchTopicResult,
  SearchTokenResult,
  ScoreBlock,
  ScoreContribution,
  SourceEventDetail,
  SourceEventsByIdsData,
  StatusData,
  WorkerStatusData,
  StockRadarRow,
  StocksRadarData,
  TimelineBucket,
  TimingBlock,
  TokenDetailMode,
  TokenCaseDossier,
  TokenCaseApiScope,
  TokenCasePostsData,
  TokenCasePostsQuery,
  TokenCaseSocialTimelineData,
  TokenCaseSocialTimelineQuery,
  TokenFactorFamily,
  TokenFactorFamilyKey,
  TokenFactorSnapshot,
  TokenFlowItem,
  TokenIntentRecord,
  TokenMarketBlock,
  TokenPostItem,
  TokenPostRange,
  TokenPostSortMode,
  TokenPostsData,
  TokenProfileBlock,
  TokenRadarFactRow,
  TokenRadarRowMeta,
  TokenReference,
  TokenResolutionRecord,
  TokenSocialTimelineData,
  TokenTimelineStage,
  TokenTimelinePost,
  TradeabilityBlock,
  WatchlistHandleOverviewData,
  WatchlistHandleRowOverview,
  WatchlistHandlesOverviewData,
  WatchlistOverviewCluster,
  WatchlistHandleTimelineData,
  WatchlistTimelineItem,
  WindowKey,
} from "./frontend-contracts";
