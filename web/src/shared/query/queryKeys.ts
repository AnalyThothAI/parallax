import type {
  ScopeKey,
  SignalPulseStatusFilter,
  SignalPulseVisibilityFilter,
  TokenPostRange,
  TokenPostServerSort,
  WatchlistTimelineScope,
  WindowKey,
} from "@lib/types";
import type { TokenRadarVenueFilter } from "@lib/venue";
import type { TokenCaseScope } from "@shared/model/tokenCaseViewModel";

export const queryKeys = {
  bootstrap: () => ["bootstrap"] as const,
  status: () => ["status"] as const,
  liveRecent: (scope: ScopeKey, handles: string) => ["recent", scope, handles] as const,
  tokenRadarRoot: () => ["token-radar"] as const,
  tokenRadar: (
    window: WindowKey,
    scope: ScopeKey,
    venue: TokenRadarVenueFilter,
    limit: number,
  ) => ["token-radar", window, scope, venue, limit] as const,
  tokenCaseRoot: () => ["token-case"] as const,
  tokenCase: (
    targetKey: string | null,
    window: WindowKey,
    scope: TokenCaseScope,
    postsLimit: number,
  ) => ["token-case", targetKey, window, scope, postsLimit] as const,
  signalLabOverview: (window: WindowKey, scope: ScopeKey) =>
    ["signal-lab-overview", window, scope] as const,
  signalPulseCompact: (
    scope: ScopeKey,
    window: WindowKey,
    visibility: SignalPulseVisibilityFilter,
  ) => ["signal-lab-pulse-compact", scope, window, visibility] as const,
  signalPulseList: (
    window: WindowKey,
    scope: ScopeKey,
    status: SignalPulseStatusFilter,
    visibility: SignalPulseVisibilityFilter,
    handle: string,
    q: string,
    limit: number,
  ) => ["signal-lab-pulse", window, scope, status, visibility, handle, q, limit] as const,
  signalPulseCandidate: (candidateId: string | null, visibility: SignalPulseVisibilityFilter) =>
    ["signal-lab-pulse-candidate", candidateId, visibility] as const,
  sourceEventsByIds: (ids: string[]) => ["events", "by-ids", [...ids].sort()] as const,
  signalLabAccountEvents: (token: string, scope: ScopeKey, handle: string) =>
    ["signal-lab-account-events", token, scope, handle] as const,
  searchInspect: (token: string, q: string, window: WindowKey, scope: ScopeKey) =>
    ["search-inspect", token, q, window, scope] as const,
  stocksRadar: (window: WindowKey, scope: ScopeKey, limit: number) =>
    ["stocks-radar", window, scope, limit] as const,
  macro: () => ["macro"] as const,
  macroModule: (moduleId: string) => ["macro", "module", moduleId] as const,
  macroSeries: (conceptKeys: string[], window: string) =>
    ["macro", "series", [...conceptKeys].sort(), window] as const,
  newsRows: ({
    cursor,
    limit,
    min_score,
    q,
    signal,
    status,
  }: {
    cursor?: string | null;
    limit: number;
    min_score?: number | null;
    q?: string | null;
    signal?: string | null;
    status?: string | null;
  }) =>
    [
      "news",
      limit,
      cursor ?? "",
      signal ?? "",
      min_score ?? "",
      status ?? "",
      q ?? "",
    ] as const,
  newsRowsInfinite: ({
    limit,
    min_score,
    q,
    signal,
    status,
  }: {
    limit: number;
    min_score?: number | null;
    q?: string | null;
    signal?: string | null;
    status?: string | null;
  }) =>
    [
      "news",
      "infinite",
      limit,
      signal ?? "",
      min_score ?? "",
      status ?? "",
      q ?? "",
    ] as const,
  newsItem: (newsItemId: string) => ["news-item", newsItemId] as const,
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
  opsDiagnostics: (window: WindowKey, scope: ScopeKey, sinceHours: number) =>
    ["ops-diagnostics", window, scope, sinceHours] as const,
  opsQueue: (queueName: string | null, status: string | null, limit: number) =>
    ["ops-queue", queueName ?? "", status ?? "", limit] as const,
  watchlistHandlesOverview: () => ["watchlist-handles-overview"] as const,
  macroAssetCorrelation: (window: string) => ["macro", "asset-correlation", window] as const,
  watchlistHandleOverview: (handle: string, scope: WatchlistTimelineScope) =>
    ["watchlist-handle-overview", handle, scope] as const,
  watchlistHandleTimeline: (handle: string, scope: WatchlistTimelineScope, limit: number) =>
    ["watchlist-handle-timeline", handle, scope, limit] as const,
};
