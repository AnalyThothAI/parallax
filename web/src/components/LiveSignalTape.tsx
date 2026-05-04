import type { AttentionFrontierItem, LivePayload, TokenFlowItem } from "../api/types";
import { compactNumber, eventHandle, eventText, formatRelativeTime, formatScore, tokenLabel } from "../lib/format";

export type LiveSignalTapeItem =
  | { kind: "event"; payload: LivePayload; score?: number | null; reason: string }
  | { kind: "token"; token: TokenFlowItem; event?: LivePayload | null; score?: number | null; reason: string }
  | { kind: "narrative"; item: AttentionFrontierItem; score?: number | null; reason: string }
  | { kind: "enrichment"; payload: LivePayload; score?: number | null; reason: string };

type LiveSignalTapeProps = {
  items: LiveSignalTapeItem[];
  selectedEventId?: string | null;
  isLoading: boolean;
  socketStatus: string;
  maxRows?: number;
  onSelect: (item: LiveSignalTapeItem) => void;
};

export function LiveSignalTape({
  items,
  selectedEventId,
  isLoading,
  socketStatus,
  maxRows = 12,
  onSelect
}: LiveSignalTapeProps) {
  const visible = items.slice(0, maxRows);
  return (
    <section className="compact-panel live-signal-tape">
      <header>
        <div>
          <h2>实时信号 Tape</h2>
        </div>
        <span>{socketStatus === "connected" ? `${items.length} 条` : "ws disconnected"}</span>
      </header>
      <div className="tape-list">
        {isLoading ? <div className="empty-state">读取 replay 中</div> : null}
        {!isLoading && visible.length === 0 ? <div className="empty-state">等待 replay 或 live event</div> : null}
        {visible.map((item) => {
          const id = tapeItemId(item);
          return (
            <button
              className={`tape-row ${selectedEventId === id ? "is-selected" : ""}`}
              key={`${item.kind}:${id}`}
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={`tape-kind ${item.kind}`}>{item.kind}</span>
              <strong>{tapeTitle(item)}</strong>
              <em className="tape-reason">{item.reason}</em>
              <b className="tape-score">{item.score !== null && item.score !== undefined ? formatScore(item.score) : "-"}</b>
              <time>{tapeTime(item)}</time>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function tapeItemId(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event?.event.event_id ?? item.token.identity.identity_key;
  }
  if (item.kind === "narrative") {
    return item.item.seed.seed_id;
  }
  return item.payload.event.event_id;
}

function tapeTitle(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    const handle = item.event ? `@${eventHandle(item.event.event)} -> ` : "";
    return `${handle}${tokenLabel(item.token)}`;
  }
  if (item.kind === "narrative") {
    const display = item.item.seed.display;
    return display?.headline_zh || "narrative_display_missing";
  }
  if (item.kind === "enrichment") {
    return `@${eventHandle(item.payload.event)} -> enrichment`;
  }
  const event = item.payload.event;
  const text = eventText(event);
  const token = event.cashtags?.[0] ? `$${event.cashtags[0]}` : text.slice(0, 28);
  return `@${eventHandle(event)} -> ${token || "event"}`;
}

function tapeTime(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    return item.event ? formatRelativeTime(item.event.event.received_at_ms) : formatRelativeTime(item.token.flow.window_end_ms);
  }
  if (item.kind === "narrative") {
    return formatRelativeTime(item.item.seed.received_at_ms);
  }
  return formatRelativeTime(item.payload.event.received_at_ms);
}

export function tokenTapeReason(token: TokenFlowItem): string {
  const reason = token.opportunity.reasons[0] ?? token.opportunity.risks[0] ?? token.social_heat.reasons[0];
  return reason ? reason.replaceAll("_", " ") : `${compactNumber(token.social_heat.mentions)} mentions`;
}
