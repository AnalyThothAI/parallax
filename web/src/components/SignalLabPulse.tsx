import { FlaskConical } from "lucide-react";
import type { SignalPulseData, SignalPulseItem, SignalPulseStatus } from "../api/types";
import { compactNumber, formatRelativeTime } from "../lib/format";

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
    return <div className="empty-state">loading signal pulse</div>;
  }
  if (!items.length) {
    return <div className="empty-state">No signal pulse items in this window</div>;
  }
  return (
    <div className={`signal-chain-list signal-pulse-list ${compact ? "compact" : ""}`}>
      {items.map((item, index) => {
        const rowKey = itemKey(item, index);
        const topRisks = stringList(item.top_risks);
        const confirmationTriggers = stringList(item.confirmation_triggers_zh);
        const invalidationTriggers = stringList(item.invalidation_triggers_zh);
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
                <p>{item.why_now_zh || item.summary_zh || "No current thesis summary."}</p>
                <span className="signal-chain-chipline">
                  {topRisks.slice(0, 2).map((risk) => (
                    <span key={`risk:${risk}`}>{risk}</span>
                  ))}
                  {confirmationTriggers.slice(0, compact ? 1 : 2).map((trigger) => (
                    <span key={`confirm:${trigger}`}>confirm: {trigger}</span>
                  ))}
                  {invalidationTriggers.slice(0, compact ? 1 : 2).map((trigger) => (
                    <span key={`invalidate:${trigger}`}>invalidate: {trigger}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{item.score_band ?? compactNumber(item.candidate_score)}</b>
                <small>{item.social_phase ?? item.narrative_type ?? item.verdict ?? "phase unknown"}</small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.updated_at_ms)}</span>
            </button>
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
  return item.symbol || item.subject_key || item.target_id || item.candidate_id || "unknown pulse";
}

function itemKey(item: SignalPulseItem, index: number): string {
  return item.candidate_id || item.target_id || item.subject_key || item.symbol || `pulse:${index}`;
}

function fullPulseMeta(item: SignalPulseItem): string {
  return [item.verdict, item.social_phase, item.score_band, `updated ${formatRelativeTime(item.updated_at_ms)} ago`].filter(Boolean).join(" · ");
}

function compactPulseMeta(item: SignalPulseItem): string {
  return [item.social_phase, item.score_band, `${formatRelativeTime(item.updated_at_ms)} ago`].filter(Boolean).join(" · ");
}

function statusLabel(status: SignalPulseStatus): string {
  if (status === "trade_candidate") return "trade";
  if (status === "token_watch") return "token";
  if (status === "theme_watch") return "theme";
  return "rejected";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : [];
}
