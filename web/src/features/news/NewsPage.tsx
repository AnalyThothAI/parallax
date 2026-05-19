import { formatRelativeTime } from "@lib/format";
import { newsLifecycleLabel, newsTokenLaneLabel } from "@shared/model/newsIntel";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { ExternalLink } from "lucide-react";

import "./news.css";
import { useNewsPage } from "./useNewsPage";

export function NewsPage() {
  const query = useNewsPage();
  const rows = query.data?.items ?? [];

  return (
    <section className="radar-panel news-panel" aria-label="News intel">
      <header className="radar-toolbar news-toolbar">
        <div>
          <h2>News</h2>
          <span>
            NEWS INTEL <b>{rows.length}</b>
          </span>
        </div>
        <div className="news-health" aria-label="news health">
          <span>{query.isFetching ? "refreshing" : "live"}</span>
        </div>
      </header>

      <div className="news-tape" aria-label="News tape">
        {query.isLoading ? <RemoteState.Loading label="loading news" layout="panel" rows={8} /> : null}
        {!query.isLoading && rows.length === 0 ? (
          query.isError ? (
            <RemoteState.Error error={query.error ?? "News unavailable"} />
          ) : (
            <RemoteState.Empty title="No news yet" />
          )
        ) : null}
        {rows.map((row) => (
          <article className="news-row" key={row.row_id}>
            <div className="news-row__meta">
              <span>{row.source_domain || "source"}</span>
              <span>{newsLifecycleLabel(row.lifecycle_status)}</span>
              {row.latest_at_ms ? <span>{formatRelativeTime(row.latest_at_ms)} ago</span> : null}
            </div>
            <div className="news-row__body">
              <h3>{row.headline}</h3>
              {row.summary ? <p>{row.summary}</p> : null}
            </div>
            <div className="news-row__footer">
              <div className="news-row__lanes">
                {(row.token_lanes ?? []).map((lane, index) => (
                  <span
                    className={clsx("news-chip", lane.lane === "resolved" ? "resolved" : "attention")}
                    key={`${row.row_id}-token-${index}`}
                  >
                    {newsTokenLaneLabel(lane)}
                  </span>
                ))}
                {(row.fact_lanes ?? []).map((lane, index) => (
                  <span className={clsx("news-chip", lane.status || "attention")} key={`${row.row_id}-fact-${index}`}>
                    {lane.event_type || "fact"} · {lane.status || "attention"}
                  </span>
                ))}
              </div>
              {row.canonical_url ? (
                <a className="news-link" href={row.canonical_url} rel="noreferrer" target="_blank">
                  <ExternalLink aria-hidden />
                </a>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
