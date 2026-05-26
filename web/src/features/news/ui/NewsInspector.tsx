import { formatRelativeTime } from "@lib/format";
import type { NewsRow } from "@shared/model/newsIntel";
import { ExternalLink } from "lucide-react";
import type { CSSProperties } from "react";

import {
  newsSignalLabel,
  newsSignalTone,
  tokenImpactLabel,
  tokenImpactTone,
} from "../model/newsSignalViewModel";

type NewsInspectorProps = {
  item: NewsRow | null;
  onFilterToken?: (symbol: string) => void;
  onOpen: (newsItemId: string) => void;
};

export function NewsInspector({ item, onFilterToken, onOpen }: NewsInspectorProps) {
  if (!item) {
    return (
      <aside className="news-tape-inspector" aria-label="news inspector">
        <p className="news-tape-empty-copy">Select a row to inspect provider facts.</p>
      </aside>
    );
  }

  return (
    <aside className="news-tape-inspector" aria-label="news inspector">
      <div className="news-tape-inspector-head">
        <span>Provider signal</span>
        <b className={newsSignalTone(item.signal)}>{newsSignalLabel(item.signal)}</b>
      </div>
      <h2>{item.headline}</h2>
      <p>{item.signal.summary_zh || item.summary || "No provider summary available."}</p>
      <dl className="news-tape-provider-fields">
        <div>
          <dt>Direction</dt>
          <dd>{newsSignalLabel(item.signal)}</dd>
        </div>
        <div>
          <dt>Method</dt>
          <dd>{item.signal.method || item.signal.source}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{item.source_domain || item.source?.source_domain || "unknown"}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{item.latest_at_ms ? `${formatRelativeTime(item.latest_at_ms)} ago` : "missing"}</dd>
        </div>
      </dl>
      <div className="news-tape-token-impact-list" aria-label="token impacts">
        {item.token_lanes.length ? (
          item.token_lanes.map((lane, index) => (
            <div
              className={`news-tape-token-impact ${tokenImpactTone(lane)}`}
              key={`${lane.symbol ?? lane.target_id ?? "token"}-${index}`}
            >
              <div>
                <b>{lane.symbol || lane.target_id || "token"}</b>
                <span>{lane.market_type || lane.resolution_status || lane.lane}</span>
              </div>
              <strong>{tokenImpactLabel(lane)}</strong>
              {lane.provider_score != null ? (
                <span
                  className="news-tape-token-bar"
                  style={
                    {
                      "--news-tape-token-score": `${Math.min(100, Math.max(0, lane.provider_score))}%`,
                    } as CSSProperties
                  }
                />
              ) : null}
              {lane.symbol ? (
                <button type="button" onClick={() => onFilterToken?.(lane.symbol ?? "")}>
                  Filter {lane.symbol}
                </button>
              ) : null}
            </div>
          ))
        ) : (
          <p className="news-tape-empty-copy">No token impact attached.</p>
        )}
      </div>
      <div className="news-tape-inspector-actions">
        <button type="button" onClick={() => onOpen(item.news_item_id)}>
          Open detail
        </button>
        {item.canonical_url ? (
          <a href={item.canonical_url} rel="noreferrer" target="_blank">
            <ExternalLink aria-hidden />
            Original
          </a>
        ) : null}
      </div>
    </aside>
  );
}
