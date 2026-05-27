export type EquityEventRouteView = "feed" | "calendar";

export type EquityEventRouteState = {
  view: EquityEventRouteView;
  selectedEventId: string | null;
  ticker: string | null;
  event_type: string | null;
  priority: string | null;
  status: string | null;
  q: string | null;
  cursor: string | null;
};

export const EQUITY_EVENT_ROUTE_DEFAULTS: EquityEventRouteState = {
  view: "feed",
  selectedEventId: null,
  ticker: null,
  event_type: null,
  priority: null,
  status: null,
  q: null,
  cursor: null,
};

export const parseEquityEventRouteState = (
  params: URLSearchParams,
  routeTail = "",
): EquityEventRouteState => {
  const detailMatch = routeTail.match(/^events\/([^/]+)$/);
  const routeView = routeTail === "calendar" ? "calendar" : parseView(params.get("view"));
  return {
    view: detailMatch ? "feed" : routeView,
    selectedEventId: detailMatch ? decodeURIComponent(detailMatch[1] ?? "") : null,
    ticker: textParam(params.get("ticker"))?.toUpperCase() ?? null,
    event_type: textParam(params.get("event_type")),
    priority: textParam(params.get("priority"))?.toUpperCase() ?? null,
    status: textParam(params.get("status")),
    q: textParam(params.get("q")),
    cursor: textParam(params.get("cursor")),
  };
};

export const serializeEquityEventRouteState = (state: EquityEventRouteState): URLSearchParams => {
  const params = new URLSearchParams();
  if (state.view !== EQUITY_EVENT_ROUTE_DEFAULTS.view) params.set("view", state.view);
  if (state.ticker) params.set("ticker", state.ticker);
  if (state.event_type) params.set("event_type", state.event_type);
  if (state.priority) params.set("priority", state.priority);
  if (state.status) params.set("status", state.status);
  if (state.q) params.set("q", state.q);
  if (state.cursor) params.set("cursor", state.cursor);
  return params;
};

const parseView = (value: string | null): EquityEventRouteView =>
  value === "calendar" ? "calendar" : "feed";

const textParam = (value: string | null): string | null => {
  const normalized = value?.trim();
  return normalized ? normalized : null;
};
