import { formatRelativeTime } from "@lib/format";
import type { NewsRow } from "@shared/model/newsIntel";
import { ExternalLink } from "lucide-react";

import {
  newsSignalLabel,
  newsSignalScoreLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenImpactTone,
} from "../model/newsSignalViewModel";
import "./newsTape.css";

type NewsTapeProps = {
  rows: NewsRow[];
  selectedId: string | null;
  onSelect: (newsItemId: string) => void;
  onOpen: (newsItemId: string) => void;
};

export function NewsTape({ rows, selectedId, onOpen, onSelect }: NewsTapeProps) {
  return (
    <div className="news-tape-list" role="list" aria-label="news tape">
      {rows.map((row) => {
        const selected = row.news_item_id === selectedId;
        return (
          <div className={`news-tape-row ${selected ? "is-selected" : ""}`} key={row.row_id}>
            <button
              aria-label={`Select news item ${row.headline}`}
              className="news-tape-row-main"
              type="button"
              onClick={() => onSelect(row.news_item_id)}
            >
              <span className="news-tape-time">
                <b>
                  {row.latest_at_ms
                    ? `${formatRelativeTime(row.latest_at_ms)} ago`
                    : "time missing"}
                </b>
                <small>{row.source_domain ?? "source unknown"}</small>
              </span>
              <span className={`news-tape-signal ${newsSignalTone(row.signal)}`}>
                <b>{newsSignalLabel(row.signal)}</b>
                <small>{newsSignalScoreLabel(row.signal)}</small>
              </span>
              <span className="news-tape-copy">
                <strong>{row.headline}</strong>
                <small>{row.signal.summary_zh || row.summary || "No summary available."}</small>
              </span>
              <span className="news-tape-token-strip">
                {row.token_lanes.slice(0, 4).map((lane, index) => (
                  <span
                    className={`news-tape-token ${tokenImpactTone(lane)}`}
                    key={`${row.news_item_id}-${lane.symbol ?? lane.target_id ?? index}`}
                  >
                    <b>{lane.symbol || lane.target_id || "token"}</b>
                    <small>{tokenImpactLabel(lane)}</small>
                  </span>
                ))}
              </span>
            </button>
            <button
              aria-label={`Open ${row.headline}`}
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
