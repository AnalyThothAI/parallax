import { formatRelativeTime } from "@lib/format";
import { ExternalLink } from "lucide-react";

import { newsLifecycleTone, tokenLaneLabel, type NewsFactRow } from "../model/newsFactViewModel";
import "./newsTape.css";

type NewsTapeProps = {
  rows: NewsFactRow[];
  onOpen: (newsItemId: string) => void;
};

export function NewsTape({ rows, onOpen }: NewsTapeProps) {
  return (
    <div className="news-tape-list" role="list" aria-label="news tape">
      {rows.map((row) => {
        const tokens = row.token_lanes;
        const visibleTokens = tokens.slice(0, 5);
        const overflowCount = Math.max(0, tokens.length - visibleTokens.length);
        const displayTitle = row.headline;
        const rating = row.provider_rating;
        const ratingProvider = rating?.provider?.toUpperCase() || "PROVIDER";
        return (
          <div className="news-tape-row" key={row.row_id}>
            <button
              aria-label={`Open news item ${displayTitle}`}
              className="news-tape-row-main"
              type="button"
              onClick={() => onOpen(row.news_item_id)}
            >
              <span className="news-tape-time">
                <b>
                  {row.latest_at_ms
                    ? `${formatRelativeTime(row.latest_at_ms)} ago`
                    : "time missing"}
                </b>
                <small>{row.source_domain ?? "source unknown"}</small>
              </span>
              <span className={`news-tape-state ${newsLifecycleTone(row.lifecycle_status)}`}>
                <b>{row.lifecycle_status}</b>
                <small>{row.content_class}</small>
              </span>
              <span className="news-tape-copy">
                <strong>{displayTitle}</strong>
                <small>
                  {rating?.score != null ? (
                    <span
                      className="news-tape-provider-rating"
                      title={`${ratingProvider} provider rating ${rating.score}`}
                    >
                      <b>{rating.score}</b>
                      <span>{ratingProvider}</span>
                    </span>
                  ) : null}
                  <span className="news-tape-summary-text">
                    {row.summary || "No source summary available."}
                  </span>
                  <span>{row.story.member_count} story members</span>
                </small>
              </span>
              <span className="news-tape-token-strip">
                {visibleTokens.map((lane, index) => (
                  <span
                    className="news-tape-token is-neutral"
                    key={`${row.news_item_id}-${lane.symbol ?? lane.target_id ?? index}`}
                    title={`${lane.symbol || lane.target_id || "token"} · ${tokenLaneLabel(lane)}`}
                  >
                    <b>{lane.symbol || lane.target_id || "token"}</b>
                    <small>{tokenLaneLabel(lane)}</small>
                  </span>
                ))}
                {overflowCount ? (
                  <span className="news-tape-token-more">+{overflowCount}</span>
                ) : null}
              </span>
            </button>
            <button
              aria-label={`Open ${displayTitle}`}
              className="news-tape-open"
              type="button"
              onClick={() => onOpen(row.news_item_id)}
            >
              <ExternalLink aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
