import type {
  ScopeKey,
  SignalPulseStatusFilter,
  TokenPostRange,
  TokenPostServerSort,
  WatchlistTimelineScope,
  WindowKey,
} from "@lib/types";
import type { TokenCaseScope } from "@shared/model/tokenCaseViewModel";

export const queryKeys = {
  bootstrap: () => ["bootstrap"] as const,
  status: () => ["status"] as const,
  liveRecent: (scope: ScopeKey, handles: string) => ["recent", scope, handles] as const,
  tokenRadarRoot: () => ["token-radar"] as const,
  tokenRadar: (window: WindowKey, scope: ScopeKey, limit: number) =>
    ["token-radar", window, scope, limit] as const,
  tokenCaseRoot: () => ["token-case"] as const,
  tokenCase: (
    targetKey: string | null,
    window: WindowKey,
    scope: TokenCaseScope,
    postsLimit: number,
  ) => ["token-case", targetKey, window, scope, postsLimit] as const,
  signalLabOverview: (window: WindowKey, scope: ScopeKey) =>
    ["signal-lab-overview", window, scope] as const,
  signalPulseCompact: (scope: ScopeKey, window: WindowKey) =>
    ["signal-lab-pulse-compact", scope, window] as const,
  signalPulseList: (
    window: WindowKey,
    scope: ScopeKey,
    status: SignalPulseStatusFilter,
    handle: string,
    q: string,
    limit: number,
  ) => ["signal-lab-pulse", window, scope, status, handle, q, limit] as const,
  signalPulseCandidate: (candidateId: string | null) =>
    ["signal-lab-pulse-candidate", candidateId] as const,
  sourceEventsByIds: (ids: string[]) => ["social-events", "by-ids", [...ids].sort()] as const,
  signalLabAccountEvents: (token: string, scope: ScopeKey, handle: string) =>
    ["signal-lab-account-events", token, scope, handle] as const,
  searchInspect: (token: string, q: string, window: WindowKey, scope: ScopeKey) =>
    ["search-inspect", token, q, window, scope] as const,
  stocksRadar: (window: WindowKey, scope: ScopeKey, limit: number) =>
    ["stocks-radar", window, scope, limit] as const,
  targetSocialTimeline: (targetKey: string | null, window: WindowKey, scope: ScopeKey) =>
    ["target-social-timeline", targetKey, window, scope] as const,
  targetPosts: (
    targetKey: string | null,
    window: WindowKey,
    scope: ScopeKey | TokenCaseScope,
    range: TokenPostRange,
    sort: TokenPostServerSort,
    limit: number,
  ) => ["target-posts", targetKey, window, scope, range, sort, limit] as const,
  accountQuality: (handles: string) => ["account-quality", handles] as const,
  notifications: () => ["notifications"] as const,
  notificationSummary: () => ["notification-summary"] as const,
  watchlistHandleSummary: (handle: string) => ["watchlist-handle-summary", handle] as const,
  watchlistHandleTimeline: (handle: string, scope: WatchlistTimelineScope, limit: number) =>
    ["watchlist-handle-timeline", handle, scope, limit] as const,
};
