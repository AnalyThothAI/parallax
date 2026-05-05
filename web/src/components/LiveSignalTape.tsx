import type { AttentionSeedItem, HarnessSnapshotItem, LivePayload, SocialEventItem, TokenFlowItem } from "../api/types";
import { compactNumber, eventHandle, eventText, formatRelativeTime, formatScore, tokenLabel } from "../lib/format";

type LiveSignalTapeBase = {
  score?: number | null;
  reason: string;
  body?: string | null;
};

export type LiveSignalTapeItem =
  | (LiveSignalTapeBase & { kind: "event"; payload: LivePayload })
  | (LiveSignalTapeBase & { kind: "token"; token: TokenFlowItem; event?: LivePayload | null })
  | (LiveSignalTapeBase & { kind: "social_event"; item: SocialEventItem })
  | (LiveSignalTapeBase & { kind: "attention_seed"; item: AttentionSeedItem })
  | (LiveSignalTapeBase & { kind: "harness_snapshot"; item: HarnessSnapshotItem });

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
              className={`tape-row ${selectedEventId === id ? "selected" : ""}`}
              key={`${item.kind}:${id}`}
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={`tape-kind ${item.kind}`}>{item.kind}</span>
              <span className="tape-main">
                <strong>{tapeTitle(item)}</strong>
                <p>{tapeBody(item)}</p>
                <em className="tape-reason">{item.reason}</em>
              </span>
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
  if (item.kind === "social_event") {
    return item.item.extraction_id;
  }
  if (item.kind === "attention_seed") {
    return item.item.seed_id;
  }
  if (item.kind === "harness_snapshot") {
    return item.item.snapshot_id;
  }
  return item.payload.event.event_id;
}

function tapeTitle(item: LiveSignalTapeItem): string {
  if (item.kind === "token") {
    const handle = item.event ? `@${eventHandle(item.event.event)} -> ` : "";
    return `${handle}${tokenLabel(item.token)}`;
  }
  if (item.kind === "social_event") {
    return `@${item.item.author_handle ?? "watched"} · ${item.item.event_type}`;
  }
  if (item.kind === "attention_seed") {
    return `@${item.item.author_handle ?? "watched"} · ${item.item.seed_status}`;
  }
  if (item.kind === "harness_snapshot") {
    return `${item.item.asset} · shadow ${item.item.shadow_signal}`;
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
  if (item.kind === "social_event") {
    return formatRelativeTime(item.item.received_at_ms);
  }
  if (item.kind === "attention_seed") {
    return formatRelativeTime(item.item.received_at_ms);
  }
  if (item.kind === "harness_snapshot") {
    return formatRelativeTime(item.item.decision_time_ms);
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
  if (item.kind === "social_event") {
    return item.item.summary_zh || item.item.subject || "extracted social event";
  }
  if (item.kind === "attention_seed") {
    return `${item.item.subject} · links ${item.item.top_linked_symbols.join(", ") || "-"}`;
  }
  if (item.kind === "harness_snapshot") {
    return `score ${item.item.combined_score.toFixed(2)} · ${item.item.horizon} · ${item.item.outcome_status}`;
  }
  return eventText(item.payload.event) || "public stream event";
}

export function tokenTapeReason(token: TokenFlowItem): string {
  const reason = token.opportunity.reasons[0] ?? token.opportunity.risks[0] ?? token.social_heat.reasons[0];
  return reason ? reason.replaceAll("_", " ") : `${compactNumber(token.social_heat.mentions)} mentions`;
}
