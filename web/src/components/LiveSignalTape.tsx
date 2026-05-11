import type { LiveSignalTapeItem } from "../features/live/liveTapeModel";
import { tapeItemId, tokenTapeReason } from "../features/live/liveTapeModel";
import {
  compactNumber,
  eventHandle,
  eventText,
  formatRelativeTime,
  formatScore,
  tokenLabel,
} from "../lib/format";

type LiveSignalTapeProps = {
  items: LiveSignalTapeItem[];
  selectedEventId?: string | null;
  isLoading: boolean;
  socketStatus: string;
  maxRows?: number;
  mobileTaskPanel?: "tape";
  onSelect: (item: LiveSignalTapeItem) => void;
};

export function LiveSignalTape({
  items,
  selectedEventId,
  isLoading,
  socketStatus,
  maxRows = 12,
  mobileTaskPanel,
  onSelect,
}: LiveSignalTapeProps) {
  const visible = items.slice(0, maxRows);
  return (
    <section className="compact-panel live-signal-tape" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <h2>实时信号 Tape</h2>
        </div>
        <span>{socketStatus === "connected" ? `${items.length} 条` : "ws disconnected"}</span>
      </header>
      <div className="tape-list">
        {isLoading ? <div className="empty-state">读取 replay 中</div> : null}
        {!isLoading && visible.length === 0 ? (
          <div className="empty-state">等待 replay 或 live event</div>
        ) : null}
        {visible.map((item) => {
          const id = tapeItemId(item);
          return (
            <button
              className={`tape-row ${selectedEventId === id ? "selected" : ""}`}
              key={`${item.kind}:${id}`}
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={`tape-kind ${item.kind}`}>{tapeKindLabel(item)}</span>
              <span className="tape-main">
                <strong>{tapeTitle(item)}</strong>
                <p>{tapeBody(item)}</p>
                <em className="tape-reason">{item.reason}</em>
              </span>
              <b className="tape-score">
                {item.score !== null && item.score !== undefined ? formatScore(item.score) : "-"}
              </b>
              <time>{tapeTime(item)}</time>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function tapeTitle(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    const handle = item.event ? `@${eventHandle(item.event.event)} -> ` : "";
    return `${handle}${tokenLabel(item.token)}`;
  }
  const event = item.payload.event;
  const text = eventText(event);
  const token = event.cashtags?.[0] ? `$${event.cashtags[0]}` : text.slice(0, 28);
  return `@${eventHandle(event)} -> ${token || "event"}`;
}

function tapeKindLabel(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return "TOKEN";
  }
  return "POST";
}

function tapeTime(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event
      ? formatRelativeTime(item.event.event.received_at_ms)
      : formatRelativeTime(item.token.flow.window_end_ms);
  }
  return formatRelativeTime(item.payload.event.received_at_ms);
}

function tapeBody(item: LiveSignalTapeItem): string {
  if (item.body?.trim()) {
    return item.body.trim();
  }
  if (item.kind === "token") {
    if (item.event) {
      return eventText(item.event.event) || tokenTapeReason(item.token);
    }
    return `${compactNumber(item.token.social_heat.mentions)} 帖 · ${tokenTapeReason(item.token)}`;
  }
  return eventText(item.payload.event) || "public stream event";
}
