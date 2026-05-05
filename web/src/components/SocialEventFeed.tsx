import type { SocialEventItem } from "../api/types";
import { formatPercentShare, formatRelativeTime } from "../lib/format";

type SocialEventFeedProps = {
  compact?: boolean;
  items: SocialEventItem[];
  selectedId?: string | null;
  onSelect: (item: SocialEventItem) => void;
};

export function SocialEventFeed({ compact, items, selectedId, onSelect }: SocialEventFeedProps) {
  if (items.length === 0) {
    return <div className="empty-state">当前窗口暂无 social event</div>;
  }
  return (
    <div className={`harness-feed ${compact ? "compact" : ""}`}>
      {items.map((item) => (
        <button
          className={`harness-row ${selectedId === item.extraction_id ? "selected" : ""}`}
          key={item.extraction_id}
          type="button"
          onClick={() => onSelect(item)}
        >
          <span className="harness-kind">EVT</span>
          <span className="harness-row-main">
            <strong>
              @{item.author_handle ?? "watched"} · {item.event_type}
            </strong>
            <p>{item.subject || item.summary_zh || "no subject"}</p>
            <span className="harness-chip-line">
              {item.anchor_terms.slice(0, 3).map((anchor) => (
                <span className="harness-anchor-chip" key={`${anchor.role}:${anchor.term}`}>
                  {anchor.term}
                </span>
              ))}
              {item.semantic_risks.slice(0, 2).map((risk) => (
                <span className="harness-risk-chip" key={risk}>
                  {risk}
                </span>
              ))}
            </span>
          </span>
          <span className="harness-row-meta">
            <b>{formatPercentShare(item.confidence)}</b>
            <span>{formatRelativeTime(item.received_at_ms)}</span>
            <span>impact {formatPercentShare(item.impact_hint)}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
