import * as PageState from "@shared/ui/PageState";
import { CalendarCheck, CalendarClock, CircleDashed } from "lucide-react";

import type { EquityEventCalendarRow } from "../model/equityEventTypes";
import {
  equityCalendarStatusLabel,
  equityEventTimestampLabel,
  equityEventTypeLabel,
} from "../model/equityEventViewModel";

export function EquityEventCalendar({
  error,
  isError,
  isFetching,
  isLoading,
  rows,
}: {
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isLoading: boolean;
  rows: EquityEventCalendarRow[];
}) {
  if (isLoading && !rows.length) {
    return <PageState.Loading layout="panel" rows={8} label="loading earnings calendar" />;
  }
  if (isError) {
    return <PageState.Error error={error ?? "Equity event calendar unavailable"} />;
  }
  if (!rows.length) {
    return (
      <PageState.Empty title="No calendar rows" hint="No expected events match these filters." />
    );
  }

  return (
    <PageState.Stale updating={isFetching && !isLoading}>
      <div className="equity-event-calendar" role="list" aria-label="earnings calendar rows">
        {rows.map((row) => (
          <article className="equity-event-calendar-row" key={row.expected_event_id}>
            <span className="equity-event-calendar-icon">{statusIcon(row.status)}</span>
            <div className="equity-event-calendar-main">
              <strong>{row.headline}</strong>
              <small>
                {row.ticker} · {row.fiscal_period ?? "period n/a"} ·{" "}
                {equityEventTypeLabel(row.event_type)}
              </small>
            </div>
            <span className="equity-event-calendar-time">
              {equityEventTimestampLabel(row.expected_at_ms)}
            </span>
            <span className="equity-event-status">
              {equityCalendarStatusLabel(row.status)}
              {row.observed_company_event_id ? ` · ${row.observed_company_event_id}` : ""}
            </span>
          </article>
        ))}
      </div>
    </PageState.Stale>
  );
}

const statusIcon = (status: string) => {
  if (status === "matched") return <CalendarCheck aria-hidden />;
  if (status === "missed") return <CircleDashed aria-hidden />;
  return <CalendarClock aria-hidden />;
};
