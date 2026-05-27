import { earningsPath } from "@shared/routing/paths";
import * as PageState from "@shared/ui/PageState";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

import type { EquityEventDetail as EquityEventDetailModel } from "../model/equityEventTypes";
import {
  equityEventBriefStatusLabel,
  equityEventTimestampLabel,
  equityEventTypeLabel,
} from "../model/equityEventViewModel";

export function EquityEventDetail({
  error,
  isError,
  isFetching,
  isLoading,
  item,
}: {
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isLoading: boolean;
  item: EquityEventDetailModel | null;
}) {
  if (isLoading && !item) {
    return <PageState.Loading layout="panel" rows={8} label="loading equity event detail" />;
  }
  if (isError) {
    return <PageState.Error error={error ?? "Equity event detail unavailable"} />;
  }
  if (!item) {
    return <PageState.Empty title="Equity event not found" />;
  }

  return (
    <PageState.Stale updating={isFetching && !isLoading}>
      <article className="equity-event-detail" aria-label="Equity event detail">
        <header className="equity-event-detail-header">
          <Link className="equity-event-back-link" to={earningsPath()}>
            <ArrowLeft aria-hidden />
            Feed
          </Link>
          <div>
            <span className="equity-event-kicker">
              {item.ticker} · {equityEventTypeLabel(item.event_type)} ·{" "}
              {equityEventTimestampLabel(item.latest_event_at_ms)}
            </span>
            <h2>{item.headline}</h2>
          </div>
          <span className="equity-event-pill">{item.priority}</span>
        </header>

        <section className="equity-event-detail-grid">
          <div className="equity-event-panel equity-event-detail-brief">
            <div className="equity-event-section-head">
              <h3>Brief</h3>
              <span>{equityEventBriefStatusLabel(item.brief.status)}</span>
            </div>
            <p>{item.brief.summary_zh ?? "Backend brief pending."}</p>
            <p>{item.brief.event_read_zh ?? item.summary ?? "No event read available."}</p>
            <KeyValue label="Direction" value={item.brief.direction ?? "n/a"} />
            <KeyValue label="Decision" value={item.brief.decision_class ?? "n/a"} />
          </div>

          <div className="equity-event-panel">
            <div className="equity-event-section-head">
              <h3>Story</h3>
              <span>{item.story?.event_count ?? 1} events</span>
            </div>
            <p>{item.story?.representative_headline ?? "No story group attached."}</p>
          </div>

          <div className="equity-event-panel">
            <div className="equity-event-section-head">
              <h3>Facts</h3>
              <span>{item.facts.length}</span>
            </div>
            <div className="equity-event-stack">
              {item.facts.map((fact, index) => (
                <div className="equity-event-fact" key={fact.fact_candidate_id ?? index}>
                  <strong>{fact.metric_name ?? fact.fact_type ?? "fact"}</strong>
                  <span>
                    {fact.value_numeric ?? fact.claim ?? "value n/a"} {fact.value_unit ?? ""}
                  </span>
                  <small>{fact.validation_status ?? "pending"}</small>
                </div>
              ))}
              {!item.facts.length ? (
                <span className="equity-event-muted">No facts projected.</span>
              ) : null}
            </div>
          </div>

          <div className="equity-event-panel">
            <div className="equity-event-section-head">
              <h3>Documents</h3>
              <span>{item.documents.length}</span>
            </div>
            <div className="equity-event-stack">
              {item.documents.map((document, index) => (
                <div className="equity-event-document" key={document.event_document_id ?? index}>
                  <span>{document.document_type ?? document.form_type ?? "document"}</span>
                  {document.document_url ? (
                    <a href={document.document_url} rel="noreferrer" target="_blank">
                      Open <ExternalLink aria-hidden />
                    </a>
                  ) : null}
                </div>
              ))}
              {!item.documents.length ? (
                <span className="equity-event-muted">No source documents.</span>
              ) : null}
            </div>
          </div>

          <div className="equity-event-panel equity-event-detail-spans">
            <div className="equity-event-section-head">
              <h3>Spans</h3>
              <span>{item.spans.length}</span>
            </div>
            <div className="equity-event-stack">
              {item.spans.map((span, index) => (
                <blockquote className="equity-event-span" key={span.span_id ?? index}>
                  {span.evidence_quote ?? "No quote text."}
                  <small>
                    {span.confidence !== null ? `confidence ${span.confidence}` : "confidence n/a"}
                  </small>
                </blockquote>
              ))}
              {!item.spans.length ? (
                <span className="equity-event-muted">No spans projected.</span>
              ) : null}
            </div>
          </div>
        </section>
      </article>
    </PageState.Stale>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="equity-event-key-value">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
