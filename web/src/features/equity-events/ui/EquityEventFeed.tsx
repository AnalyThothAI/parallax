import * as PageState from "@shared/ui/PageState";
import { Bot, ChevronRight, FileText, ShieldAlert } from "lucide-react";

import type { EquityEventFeedModel } from "../model/equityEventViewModel";
import {
  equityEventBriefStatusLabel,
  equityEventSourceLabel,
  equityEventTimestampLabel,
  equityEventTypeLabel,
} from "../model/equityEventViewModel";

export function EquityEventFeed({
  error,
  isError,
  isFetching,
  isLoading,
  model,
  nextCursor,
  onLoadMore,
  onOpen,
}: {
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isLoading: boolean;
  model: EquityEventFeedModel;
  nextCursor: string | null;
  onLoadMore: (cursor: string) => void;
  onOpen: (eventId: string) => void;
}) {
  if (isLoading && !model.rows.length) {
    return <PageState.Loading layout="panel" rows={8} label="loading equity events" />;
  }
  if (isError) {
    return <PageState.Error error={error ?? "Equity events unavailable"} />;
  }
  if (!model.rows.length) {
    return (
      <PageState.Empty
        title={model.emptyTitle}
        hint="The equity event read model returned no rows for the current filters."
      />
    );
  }

  return (
    <PageState.Stale updating={isFetching && !isLoading}>
      <div className="equity-event-feed">
        <div className="equity-event-feed-summary" aria-label="Equity event feed summary">
          <span>{model.summary.total} rows</span>
          <span>{model.summary.p0} P0</span>
          <span>{model.summary.ready} ready</span>
          <span>{model.summary.pending} pending</span>
          <span>{model.summary.drivers} drivers</span>
          {nextCursor ? <span>next page</span> : <span>latest page</span>}
        </div>
        {nextCursor ? (
          <div className="equity-event-feed-actions">
            <button
              className="equity-event-load-more"
              type="button"
              onClick={() => onLoadMore(nextCursor)}
            >
              Load more
            </button>
          </div>
        ) : null}
        <div className="equity-event-feed-head" aria-hidden="true">
          <span>Time</span>
          <span>Event</span>
          <span>Priority</span>
          <span>Brief</span>
          <span>Evidence</span>
        </div>
        <div className="equity-event-feed-list" role="list" aria-label="earnings event feed">
          {model.rows.map((row) => (
            <button
              className="equity-event-feed-row"
              key={row.company_event_id}
              type="button"
              onClick={() => onOpen(row.company_event_id)}
            >
              <span className="equity-event-time">{equityEventTimestampLabel(row.latest_event_at_ms)}</span>
              <span className="equity-event-main">
                <strong>{row.headline}</strong>
                <small>
                  {row.ticker} · {row.company_name ?? "company"} · {equityEventTypeLabel(row.event_type)}
                </small>
                <em>{row.brief.summary_zh ?? row.summary ?? "Backend brief pending."}</em>
              </span>
              <span className="equity-event-pill">{row.priority}</span>
              <span className="equity-event-status">
                <Bot aria-hidden />
                {equityEventBriefStatusLabel(row.brief.status)}
              </span>
              <span className="equity-event-evidence">
                <FileText aria-hidden />
                {row.documents.length}
                <ShieldAlert aria-hidden />
                {row.facts.length}
              </span>
              <span className="equity-event-source">{equityEventSourceLabel(row.source_role)}</span>
              <ChevronRight className="equity-event-row-arrow" aria-hidden />
            </button>
          ))}
        </div>
      </div>
    </PageState.Stale>
  );
}
