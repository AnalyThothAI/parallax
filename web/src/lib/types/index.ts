import type { components } from "./openapi";

export type { components, operations, paths } from "./openapi";

export type ApiResponse<T> = {
  ok: boolean;
  data: T;
  error?: string | null;
  field?: string | null;
};

export type BootstrapData = components["schemas"]["BootstrapData"];
export type StatusData = components["schemas"]["StatusData"];
export type RecentData = components["schemas"]["RecentData"];
export type SearchData = components["schemas"]["SearchData"];
export type SearchInspectData = components["schemas"]["SearchInspectData"];
export type TokenRadarData = components["schemas"]["TokenRadarData"];
export type StocksRadarData = components["schemas"]["StocksRadarData"];
export type LiveMarketData = components["schemas"]["LiveMarketData"];
export type TargetPostsData = components["schemas"]["TargetPostsData"];
export type TargetSocialTimelineData = components["schemas"]["TargetSocialTimelineData"];
export type AccountAlertsData = components["schemas"]["AccountAlertsData"];
export type AccountQualityData = components["schemas"]["AccountQualityData"];
export type NotificationSummary = components["schemas"]["NotificationSummary"];
export type NotificationsData = components["schemas"]["NotificationsData"];
export type NotificationReadData = components["schemas"]["NotificationReadData"];
export type NotificationReadAllData = components["schemas"]["NotificationReadAllData"];
export type SignalPulseData = components["schemas"]["SignalPulseData"];
export type SignalPulseItem = components["schemas"]["SignalPulseItem"];

// local-ui-contract: these UI/domain shapes still encode frontend-specific view models.
export type {
  AlertRecord,
  Decision,
  EntityRecord,
  EventRecord,
  LiveMarketUpdatePayload,
  LivePayload,
  MarketCandle,
  MarketContext,
  MarketObservationSnapshot,
  NotificationItem,
  NotificationLivePayload,
  RadarSortMode,
  ScopeKey,
  SearchAgentBrief,
  SearchItem,
  SearchTargetCandidate,
  SearchTopicResult,
  SearchTokenResult,
  ScoreBlock,
  SignalPulseStatus,
  SignalPulseStatusFilter,
  StockRadarRow,
  TimelineBucket,
  TimingBlock,
  TokenDetailMode,
  TokenDetailTab,
  TokenFactorFamily,
  TokenFactorFamilyKey,
  TokenFactorSnapshot,
  TokenFlowItem,
  TokenMarketBlock,
  TokenPostRange,
  TokenPostServerSort,
  TokenPostSortMode,
  TokenPostsData,
  TokenProfileBlock,
  TokenReference,
  TokenSocialTimelineData,
  TokenTimelinePost,
  WindowKey,
} from "../../api/types";
