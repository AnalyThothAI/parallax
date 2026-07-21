import { formatRelativeTime } from "@lib/format";
import type { NewsRow } from "@shared/model/newsIntel";
import { ExternalLink } from "lucide-react";

import {
  newsAgentReviewBadge,
  newsDisplayTokenLanes,
  newsSignalLabel,
  newsSignalStatusLabel,
  newsSignalTone,
  tokenMarketLabel,
} from "../model/newsSignalViewModel";
import "./newsTape.css";

type NewsTapeProps = {
  rows: NewsRow[];
  onOpen: (newsItemId: string) => void;
};

export function NewsTape({ rows, onOpen }: NewsTapeProps) {
  return (
    <div className="news-tape-list" role="list" aria-label="news tape">
      {rows.map((row) => {
        const tokens = newsDisplayTokenLanes(row);
        const visibleTokens = tokens.slice(0, 5);
        const overflowCount = Math.max(0, tokens.length - visibleTokens.length);
        const reviewBadge = newsAgentReviewBadge(row);
        const displaySignal = row.signal.display_signal;
        const useAgentTitle = row.agent_brief.status === "ready";
        const displayTitle = useAgentTitle
          ? row.agent_brief.title_zh || displaySignal.title_zh || row.headline
          : displaySignal.title_zh || row.headline;
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
              <span className={`news-tape-signal ${newsSignalTone(displaySignal)}`}>
                <b>{newsSignalLabel(displaySignal)}</b>
                <small>{newsSignalStatusLabel(displaySignal)}</small>
              </span>
              <span className="news-tape-copy">
                <strong>{displayTitle}</strong>
                <small>
                  <span className={`news-tape-review ${reviewBadge.tone}`}>
                    {reviewBadge.label}
                  </span>
                  {rating?.score != null ? (
                    <span
                      className="news-tape-provider-rating"
                      title={`${ratingProvider} provider rating ${rating.score}`}
                    >
                      <b>{rating.score}</b>
                      <span>{ratingProvider}</span>
                    </span>
                  ) : null}
                  {reviewBadge.detail ? (
                    <span className="news-tape-review-reason" title={reviewBadge.title}>
                      {reviewBadge.detail}
                    </span>
                  ) : null}
                  <span className="news-tape-summary-text">
                    {displaySignal.summary_zh || row.summary || "No summary available."}
                  </span>
                </small>
              </span>
              <span className="news-tape-token-strip">
                {visibleTokens.map((lane, index) => (
                  <span
                    className="news-tape-token is-neutral"
                    key={`${row.news_item_id}-${lane.symbol ?? lane.target_id ?? index}`}
                    title={`${lane.symbol || lane.target_id || "token"} · ${tokenMarketLabel(lane)}`}
                  >
                    <b>{lane.symbol || lane.target_id || "token"}</b>
                    <small>{tokenMarketLabel(lane)}</small>
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
