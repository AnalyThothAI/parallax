import {
  fetchEquityEventCalendar,
  fetchEquityEventDetail,
  fetchEquityEventSummary,
  fetchEquityEvents,
} from "@lib/api/client";
import { queryKeys } from "@shared/query/queryKeys";
import { useQuery } from "@tanstack/react-query";

import type { EquityEventRouteState } from "../state/equityEventRouteState";

export const EQUITY_EVENTS_PAGE_SIZE = 100;

export const useEquityEvents = ({
  enabled = true,
  routeState,
  token,
}: {
  enabled?: boolean;
  routeState: EquityEventRouteState;
  token: string;
}) =>
  useQuery({
    enabled: Boolean(token) && enabled,
    placeholderData: (previousData) => previousData,
    queryKey: queryKeys.equityEvents({
      cursor: routeState.cursor,
      event_type: routeState.event_type,
      limit: EQUITY_EVENTS_PAGE_SIZE,
      priority: routeState.priority,
      q: routeState.q,
      status: routeState.status,
      ticker: routeState.ticker,
    }),
    queryFn: () =>
      fetchEquityEvents({
        cursor: routeState.cursor,
        event_type: routeState.event_type,
        limit: EQUITY_EVENTS_PAGE_SIZE,
        priority: routeState.priority,
        q: routeState.q,
        status: routeState.status,
        ticker: routeState.ticker,
        token,
      }),
    refetchInterval: 15_000,
    staleTime: 0,
  });

export const useEquityEventCalendar = ({
  enabled = true,
  routeState,
  token,
}: {
  enabled?: boolean;
  routeState: EquityEventRouteState;
  token: string;
}) =>
  useQuery({
    enabled: Boolean(token) && enabled,
    queryKey: queryKeys.equityEventCalendar({
      status: routeState.status,
      ticker: routeState.ticker,
    }),
    queryFn: () =>
      fetchEquityEventCalendar({
        status: routeState.status,
        ticker: routeState.ticker,
        token,
      }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

export const useEquityEventDetail = ({
  eventId,
  token,
}: {
  eventId: string | null;
  token: string;
}) =>
  useQuery({
    enabled: Boolean(token && eventId),
    queryKey: queryKeys.equityEvent(eventId ?? ""),
    queryFn: () => fetchEquityEventDetail({ eventId: eventId ?? "", token }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

export const useEquityEventSummary = ({ token }: { token: string }) =>
  useQuery({
    enabled: Boolean(token),
    queryKey: queryKeys.equityEventSummary(),
    queryFn: () => fetchEquityEventSummary({ token }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
