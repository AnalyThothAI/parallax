import {
  earningsCalendarPath,
  earningsPath,
  equityEventDetailPath,
} from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import { BarChart3, CalendarDays, FileClock, Search } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  useEquityEventCalendar,
  useEquityEventDetail,
  useEquityEventSummary,
  useEquityEvents,
} from "../api/useEquityEvents";
import {
  buildEquityEventFeedModel,
  sortEquityCalendarRows,
} from "../model/equityEventViewModel";
import {
  serializeEquityEventRouteState,
  type EquityEventRouteState,
} from "../state/equityEventRouteState";

import { EquityEventCalendar } from "./EquityEventCalendar";
import { EquityEventDetail } from "./EquityEventDetail";
import { EquityEventFeed } from "./EquityEventFeed";
import "./equityEvents.css";

export function EquityEventsRoute({
  routeState,
  token,
}: {
  routeState: EquityEventRouteState;
  token: string;
}) {
  const navigate = useNavigate();
  const summaryQuery = useEquityEventSummary({ token });
  const feedQuery = useEquityEvents({
    enabled: !routeState.selectedEventId && routeState.view === "feed",
    routeState,
    token,
  });
  const calendarQuery = useEquityEventCalendar({
    enabled: !routeState.selectedEventId && routeState.view === "calendar",
    routeState,
    token,
  });
  const detailQuery = useEquityEventDetail({
    eventId: routeState.selectedEventId,
    token,
  });
  const feedModel = buildEquityEventFeedModel(feedQuery.data?.items ?? []);
  const calendarRows = sortEquityCalendarRows(calendarQuery.data?.items ?? []);

  const updateFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const nextState: EquityEventRouteState = {
      ...routeState,
      cursor: null,
      event_type: formText(form, "event_type"),
      priority: formText(form, "priority"),
      q: formText(form, "q"),
      status: formText(form, "status"),
      ticker: formText(form, "ticker")?.toUpperCase() ?? null,
    };
    navigate(`${routeState.view === "calendar" ? earningsCalendarPath() : earningsPath()}${searchFor(nextState)}`);
  };

  return (
    <section className="equity-event-route" aria-label="Equity event intel">
      <header className="equity-event-header">
        <div className="equity-event-title-block">
          <span className="equity-event-kicker">Equity event intel</span>
          <h1>Earnings</h1>
        </div>
        <div className="equity-event-summary" aria-label="Equity event summary">
          <Metric
            icon={<BarChart3 aria-hidden />}
            label="P0 open"
            value={summaryQuery.data?.p0_open_count ?? "--"}
          />
          <Metric
            icon={<CalendarDays aria-hidden />}
            label="today"
            value={summaryQuery.data?.today_count ?? "--"}
          />
          <Metric
            icon={<FileClock aria-hidden />}
            label="brief due"
            value={summaryQuery.data?.due_brief_queue_count ?? "--"}
          />
        </div>
      </header>

      <nav className="equity-event-tabs" aria-label="Earnings views">
        <Link
          className="equity-event-tab"
          data-active={!routeState.selectedEventId && routeState.view === "feed"}
          to={`${earningsPath()}${searchFor({ ...routeState, view: "feed" })}`}
        >
          Feed
        </Link>
        <Link
          className="equity-event-tab"
          data-active={!routeState.selectedEventId && routeState.view === "calendar"}
          to={`${earningsCalendarPath()}${searchFor({ ...routeState, view: "calendar" })}`}
        >
          Calendar
        </Link>
      </nav>

      {!routeState.selectedEventId ? (
        <form className="equity-event-filters" aria-label="Equity event filters" onSubmit={updateFilters}>
          <label>
            <span>Ticker</span>
            <input name="ticker" defaultValue={routeState.ticker ?? ""} placeholder="NVDA" />
          </label>
          <label>
            <span>Type</span>
            <input
              name="event_type"
              defaultValue={routeState.event_type ?? ""}
              placeholder="earnings_release"
            />
          </label>
          <label>
            <span>Priority</span>
            <select name="priority" defaultValue={routeState.priority ?? ""}>
              <option value="">All</option>
              <option value="P0">P0</option>
              <option value="P1">P1</option>
              <option value="P2">P2</option>
              <option value="P3">P3</option>
            </select>
          </label>
          <label>
            <span>Status</span>
            <input name="status" defaultValue={routeState.status ?? ""} placeholder="ready" />
          </label>
          <label className="equity-event-filter-search">
            <span>Search</span>
            <input name="q" defaultValue={routeState.q ?? ""} placeholder="company or fact" />
          </label>
          <button className="equity-event-filter-submit" type="submit">
            <Search aria-hidden />
            Apply
          </button>
        </form>
      ) : null}

      {routeState.selectedEventId ? (
        <EquityEventDetail
          error={detailQuery.error}
          isError={detailQuery.isError}
          isFetching={detailQuery.isFetching}
          isLoading={detailQuery.isLoading}
          item={detailQuery.data ?? null}
        />
      ) : routeState.view === "calendar" ? (
        <EquityEventCalendar
          error={calendarQuery.error}
          isError={calendarQuery.isError}
          isFetching={calendarQuery.isFetching}
          isLoading={calendarQuery.isLoading}
          rows={calendarRows}
        />
      ) : (
        <EquityEventFeed
          error={feedQuery.error}
          isError={feedQuery.isError}
          isFetching={feedQuery.isFetching}
          isLoading={feedQuery.isLoading}
          model={feedModel}
          nextCursor={feedQuery.data?.next_cursor ?? null}
          onLoadMore={(cursor) =>
            navigate(`${earningsPath()}${searchFor({ ...routeState, cursor })}`)
          }
          onOpen={(eventId) => navigate(equityEventDetailPath(eventId))}
        />
      )}
      {summaryQuery.isError ? (
        <div className="equity-event-summary-error">
          <PageState.Error error={summaryQuery.error ?? "Equity event summary unavailable"} />
        </div>
      ) : null}
    </section>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="equity-event-metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

const searchFor = (state: EquityEventRouteState): string => {
  const params = serializeEquityEventRouteState(state);
  return params.toString() ? `?${params.toString()}` : "";
};

const formText = (form: FormData, key: string): string | null => {
  const value = String(form.get(key) ?? "").trim();
  return value || null;
};
