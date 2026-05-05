import type { AttentionSeedItem } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";

type AttentionSeedListProps = {
  items: AttentionSeedItem[];
  selectedSeedId?: string | null;
  onSelect: (item: AttentionSeedItem) => void;
};

export function AttentionSeedList({ items, selectedSeedId, onSelect }: AttentionSeedListProps) {
  if (items.length === 0) {
    return <div className="empty-state">当前窗口暂无 attention seed</div>;
  }
  return (
    <div className="harness-feed">
      {items.map((item) => (
        <button
          className={`harness-row ${selectedSeedId === item.seed_id ? "selected" : ""}`}
          key={item.seed_id}
          type="button"
          onClick={() => onSelect(item)}
        >
          <span className="harness-kind">SEED</span>
          <span className="harness-row-main">
            <strong>
              @{item.author_handle ?? "watched"} · {item.event_type}
            </strong>
            <p>
              {item.subject} · {item.seed_status}
            </p>
            <span className="harness-stage-line">
              <span>{item.seed_status.replaceAll("_", " ")}</span>
              <span>{item.top_linked_symbols.length ? item.top_linked_symbols.map((symbol) => `$${symbol}`).join(", ") : "no linked token"}</span>
              {item.risks[0] ? <span>{item.risks[0].replaceAll("_", " ")}</span> : null}
            </span>
          </span>
          <span className="harness-row-meta">
            <b>{compactNumber(item.token_uptake_count)} link</b>
            <span>{formatRelativeTime(item.received_at_ms)}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
