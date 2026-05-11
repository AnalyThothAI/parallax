import type { ScopeKey, SignalPulseStatusFilter, WindowKey } from "../../api/types";
import { OBSERVATION_WINDOWS } from "../../lib/observationWindows";

export type SignalLabRouteState = {
  window: WindowKey;
  scope: ScopeKey;
  status: SignalPulseStatusFilter;
  handle: string;
  q: string;
};

export const SIGNAL_LAB_ROUTE_DEFAULTS: SignalLabRouteState = {
  window: "1h",
  scope: "all",
  status: "all",
  handle: "",
  q: "",
};

const SIGNAL_LAB_STATUSES: SignalPulseStatusFilter[] = [
  "all",
  "trade_candidate",
  "token_watch",
  "theme_watch",
  "risk_rejected_high_info",
];

export function parseSignalLabRouteState(searchParams: URLSearchParams): SignalLabRouteState {
  return {
    window: parseWindow(searchParams.get("window")),
    scope: parseScope(searchParams.get("scope")),
    status: parseStatus(searchParams.get("status")),
    handle: normalizeHandle(searchParams.get("handle") ?? ""),
    q: (searchParams.get("q") ?? "").trim(),
  };
}

export function serializeSignalLabRouteState(state: SignalLabRouteState): URLSearchParams {
  const params = new URLSearchParams();
  const normalized: SignalLabRouteState = {
    window: parseWindow(state.window),
    scope: parseScope(state.scope),
    status: parseStatus(state.status),
    handle: normalizeHandle(state.handle),
    q: state.q.trim(),
  };
  if (normalized.window !== SIGNAL_LAB_ROUTE_DEFAULTS.window)
    params.set("window", normalized.window);
  if (normalized.scope !== SIGNAL_LAB_ROUTE_DEFAULTS.scope) params.set("scope", normalized.scope);
  if (normalized.status !== SIGNAL_LAB_ROUTE_DEFAULTS.status)
    params.set("status", normalized.status);
  if (normalized.handle) params.set("handle", normalized.handle);
  if (normalized.q) params.set("q", normalized.q);
  return params;
}

export function signalLabRouteSearch(state: SignalLabRouteState): string {
  const search = serializeSignalLabRouteState(state).toString();
  return search ? `?${search}` : "";
}

export function signalLabRouteStateWith(
  state: SignalLabRouteState,
  patch: Partial<SignalLabRouteState>,
): SignalLabRouteState {
  return {
    ...state,
    ...patch,
  };
}

function parseWindow(value: string | null): WindowKey {
  return OBSERVATION_WINDOWS.includes(value as WindowKey)
    ? (value as WindowKey)
    : SIGNAL_LAB_ROUTE_DEFAULTS.window;
}

function parseScope(value: string | null): ScopeKey {
  return value === "matched" || value === "all" ? value : SIGNAL_LAB_ROUTE_DEFAULTS.scope;
}

function parseStatus(value: string | null): SignalPulseStatusFilter {
  return SIGNAL_LAB_STATUSES.includes(value as SignalPulseStatusFilter)
    ? (value as SignalPulseStatusFilter)
    : SIGNAL_LAB_ROUTE_DEFAULTS.status;
}

function normalizeHandle(value: string): string {
  return value.trim().replace(/^@/, "").toLowerCase();
}
