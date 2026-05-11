import { FlaskConical } from "lucide-react";
import type { SignalPulseData, SignalPulseItem, SignalPulseStatus } from "../api/types";
import { compactNumber, formatRelativeTime, formatUsdCompact } from "../lib/format";
import { signalPulseVenueActions } from "../lib/venue";
import { SkeletonRows } from "../shared/ui/RemoteState";

type SignalLabPulseProps = {
  data?: SignalPulseData;
  isLoading?: boolean;
  selectedItemId?: string | null;
  mobileTaskPanel?: "lab";
  onOpenLab: () => void;
  onSelect: (item: SignalPulseItem) => void;
};

export function SignalLabPulse({ data, isLoading, selectedItemId, mobileTaskPanel, onOpenLab, onSelect }: SignalLabPulseProps) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const summary = data?.summary;
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
      <div className="signal-attention-summary" aria-label="signal pulse summary">
        <SummaryPill label="trade" value={summary?.trade_candidate ?? 0} />
        <SummaryPill label="token" value={summary?.token_watch ?? 0} />
        <SummaryPill label="theme" value={summary?.theme_watch ?? 0} />
        <SummaryPill label="rejected" value={summary?.risk_rejected_high_info ?? 0} />
      </div>
      <SignalPulseList compact isLoading={isLoading} items={items} selectedItemId={selectedItemId} onSelect={onSelect} />
    </section>
  );
}

type SignalPulseListProps = {
  items: SignalPulseItem[];
  selectedItemId?: string | null;
  isLoading?: boolean;
  compact?: boolean;
  onSelect: (item: SignalPulseItem) => void;
};

export function SignalPulseList({ compact, isLoading, items, selectedItemId, onSelect }: SignalPulseListProps) {
  if (isLoading) {
    return <SkeletonRows compact={compact} count={compact ? 5 : 6} label="loading signal pulse" />;
  }
  if (!items.length) {
    return <div className="empty-state">No signal pulse items in this window</div>;
  }
  return (
    <div className={`signal-chain-list signal-pulse-list ${compact ? "compact" : ""}`}>
      {items.map((item, index) => {
        const rowKey = itemKey(item, index);
        const facts = pulseFactChips(item);
        const venueActions = signalPulseVenueActions(item);
        return (
          <article className={`signal-chain-row ${selectedItemId === item.candidate_id ? "selected" : ""}`} key={rowKey}>
            <button
              aria-label={`open Signal Pulse ${itemTitle(item)}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={`signal-stage-badge ${item.pulse_status}`}>{statusLabel(item.pulse_status)}</span>
              <span className="signal-chain-main">
                <strong>{itemTitle(item)}</strong>
                <em>{compact ? compactPulseMeta(item) : fullPulseMeta(item)}</em>
                <p>{item.agent_recommendation.summary_zh || "No recommendation summary."}</p>
                <span className="signal-chain-chipline">
                  {facts.slice(0, compact ? 4 : 6).map((fact) => (
                    <span key={fact}>{fact}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{scoreBand(item) ?? compactNumber(gateScore(item))}</b>
                <small>{gateStatus(item) ?? item.agent_recommendation.recommendation ?? "gate unknown"}</small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.updated_at_ms)}</span>
            </button>
            <span className="signal-pulse-venue-links" data-signal-pulse-action="venue">
              {venueActions.map((action) => (
                <a
                  aria-label={`Open ${itemTitle(item)} on ${action.label}`}
                  className="venue-link"
                  href={action.url}
                  key={`${action.label}:${action.url}`}
                  rel="noreferrer"
                  target="_blank"
                >
                  {action.label}
                </a>
              ))}
            </span>
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

function itemTitle(item: SignalPulseItem): string {
  return item.factor_snapshot.subject.symbol || item.symbol || item.subject_key || item.target_id || item.candidate_id || "unknown pulse";
}

function itemKey(item: SignalPulseItem, index: number): string {
  return item.candidate_id || item.target_id || item.subject_key || item.symbol || `pulse:${index}`;
}

function fullPulseMeta(item: SignalPulseItem): string {
  return [marketFactMeta(item), socialFactMeta(item), gateMeta(item), `updated ${formatRelativeTime(item.updated_at_ms)} ago`]
    .filter(Boolean)
    .join(" · ");
}

function compactPulseMeta(item: SignalPulseItem): string {
  return [socialFactMeta(item), gateMeta(item), `${formatRelativeTime(item.updated_at_ms)} ago`].filter(Boolean).join(" · ");
}

function statusLabel(status: SignalPulseStatus): string {
  if (status === "trade_candidate") return "trade";
  if (status === "token_watch") return "token";
  if (status === "theme_watch") return "theme";
  return "rejected";
}

function pulseFactChips(item: SignalPulseItem): string[] {
  return [
    usdFact("cap", item.fact_card.market_cap_usd),
    usdFact("liq", item.fact_card.liquidity_usd),
    numberFact("holders", item.fact_card.holders),
    usdFact("vol", item.fact_card.volume_24h_usd),
    numberFact("mentions", item.fact_card.mentions_1h),
    numberFact("authors", item.fact_card.unique_authors),
    gateMeta(item)
  ].filter((value): value is string => Boolean(value));
}

function marketFactMeta(item: SignalPulseItem): string | null {
  return [
    usdFact("cap", item.fact_card.market_cap_usd),
    usdFact("liq", item.fact_card.liquidity_usd),
    numberFact("holders", item.fact_card.holders) ?? usdFact("vol", item.fact_card.volume_24h_usd)
  ]
    .filter(Boolean)
    .join(" · ") || null;
}

function socialFactMeta(item: SignalPulseItem): string | null {
  return [numberFact("mentions", item.fact_card.mentions_1h), numberFact("authors", item.fact_card.unique_authors)]
    .filter(Boolean)
    .join(" · ") || null;
}

function gateMeta(item: SignalPulseItem): string | null {
  const status = gateStatus(item);
  const band = scoreBand(item);
  if (status && band) return `${status} ${band}`;
  return status ?? band;
}

function gateStatus(item: SignalPulseItem): string | null {
  return stringValue(item.gate.pulse_status) ?? stringValue(item.fact_card.market_status) ?? item.pulse_status ?? null;
}

function scoreBand(item: SignalPulseItem): string | null {
  return stringValue(item.gate.score_band) ?? item.score_band ?? null;
}

function gateScore(item: SignalPulseItem): number | null {
  return numberValue(item.gate.candidate_score) ?? item.candidate_score ?? item.factor_snapshot.composite.rank_score ?? null;
}

function usdFact(label: string, value: unknown): string | null {
  const number = numberValue(value);
  return number === null ? null : `${label} ${formatUsdCompact(number)}`;
}

function numberFact(label: string, value: unknown): string | null {
  const number = numberValue(value);
  return number === null ? null : `${label} ${compactNumber(number)}`;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}
