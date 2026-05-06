import { ExternalLink, FlaskConical } from "lucide-react";
import type { TradingAttentionData, TradingAttentionItem } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";

type SignalLabPulseProps = {
  data?: TradingAttentionData;
  isLoading?: boolean;
  selectedItemId?: string | null;
  mobileTaskPanel?: "lab";
  onOpenLab: () => void;
  onSelect: (item: TradingAttentionItem) => void;
};

export function SignalLabPulse({ data, isLoading, selectedItemId, mobileTaskPanel, onOpenLab, onSelect }: SignalLabPulseProps) {
  const items = data?.items ?? [];
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Lab Pulse</h2>
        </div>
        <button className="text-action" type="button" onClick={onOpenLab}>
          Open Lab
        </button>
      </header>
      <div className="signal-attention-summary" aria-label="trading attention summary">
        <SummaryPill label="direct" value={data?.summary.direct_token ?? 0} />
        <SummaryPill label="topics" value={data?.summary.topic_heat ?? 0} />
        <SummaryPill label="risk" value={data?.summary.risk_alert ?? 0} />
      </div>
      <TradingAttentionList compact isLoading={isLoading} items={items} selectedItemId={selectedItemId} onSelect={onSelect} />
    </section>
  );
}

type TradingAttentionListProps = {
  items: TradingAttentionItem[];
  selectedItemId?: string | null;
  isLoading?: boolean;
  compact?: boolean;
  onSelect: (item: TradingAttentionItem) => void;
};

export function TradingAttentionList({ compact, isLoading, items, selectedItemId, onSelect }: TradingAttentionListProps) {
  if (isLoading) {
    return <div className="empty-state">loading trading attention</div>;
  }
  if (!items.length) {
    return <div className="empty-state">No trading attention in this window</div>;
  }
  return (
    <div className={`signal-chain-list trading-attention-list ${compact ? "compact" : ""}`}>
      {items.map((item) => {
        const sourceUrl = item.event.canonical_url;
        return (
          <article className={`signal-chain-row ${selectedItemId === item.item_id ? "selected" : ""}`} key={item.item_id}>
            <button
              aria-label={`open trading attention ${item.title}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={`signal-stage-badge ${item.kind}`}>{kindShortLabel(item.kind_label)}</span>
              <span className="signal-chain-main">
                <strong>{attentionTitle(item)}</strong>
                <em>{compact ? compactAttentionMeta(item) : fullAttentionMeta(item)}</em>
                <p>{item.summary || item.why_it_matters}</p>
                <span className="signal-chain-chipline">
                  {item.linked_tokens.slice(0, 2).map((token) => (
                    <span key={token.identity_key ?? token.token_id ?? token.symbol}>{token.symbol ?? token.identity_key}</span>
                  ))}
                  {item.linked_topics.slice(0, 3).map((topic) => (
                    <span key={topic.key}>{topic.label}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{scoreLabel(item)}</b>
                <small>
                  {compactNumber(item.metrics.window_mentions)} posts · {compactNumber(item.metrics.watched_author_count)} accts
                </small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.received_at_ms)}</span>
            </button>
            {sourceUrl ? (
              <a
                aria-label={`open source post for ${item.title}`}
                className="signal-chain-twitter-link"
                href={sourceUrl}
                rel="noreferrer"
                target="_blank"
              >
                <ExternalLink aria-hidden />
              </a>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}

function SummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <span>
      {label} <b>{compactNumber(value)}</b>
    </span>
  );
}

function attentionTitle(item: TradingAttentionItem): string {
  const source = item.source.handle ? `@${item.source.handle}` : "@watched";
  return `${source} · ${item.kind_label} -> ${item.title}`;
}

function fullAttentionMeta(item: TradingAttentionItem): string {
  return `@${item.source.handle ?? "unknown"} · ${item.priority} · updated ${formatRelativeTime(item.updated_at_ms)} ago`;
}

function compactAttentionMeta(item: TradingAttentionItem): string {
  return [
    directionLabel(item.direction_hint),
    mechanismLabel(item.attention_mechanism),
    `${formatRelativeTime(item.updated_at_ms)} ago`
  ].join(" · ");
}

function directionLabel(direction?: string | null): string {
  if (direction === "attention_positive") return "positive";
  if (direction === "attention_negative") return "negative";
  if (direction === "risk_negative") return "risk";
  if (direction === "neutral") return "neutral";
  return "unknown";
}

function mechanismLabel(mechanism?: string | null): string {
  if (mechanism === "direct_token_mention") return "direct";
  if (mechanism === "product_or_feature") return "product";
  if (mechanism === "reply_target") return "reply";
  if (mechanism === "exchange_or_listing") return "listing";
  if (mechanism === "risk_focus") return "risk";
  if (mechanism === "cultural_object") return "culture";
  if (mechanism === "meme_phrase") return "phrase";
  return "unknown";
}

function kindShortLabel(label: string): string {
  return label.toUpperCase();
}

function scoreLabel(item: TradingAttentionItem): string {
  if (item.priority === "hot") return "HOT";
  if (item.priority === "watch") return "WATCH";
  if (item.priority === "context") return "CONTEXT";
  return "MUTED";
}
