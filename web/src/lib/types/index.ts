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
  TokenFactorFamily,
  TokenFactorFamilyKey,
  TokenFactorSnapshot,
  TokenFlowItem,
  TokenIntentRecord,
  TokenMarketBlock,
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
  WindowKey,
} from "./frontend-contracts";
