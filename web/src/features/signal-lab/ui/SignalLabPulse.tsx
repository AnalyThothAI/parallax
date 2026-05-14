import { compactNumber, formatRelativeTime, formatUsdCompact, shortAddress } from "@lib/format";
import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import { signalPulseVenueActions } from "@lib/venue";
import { searchPath } from "@shared/routing/paths";
import { RemoteState, SkeletonRows } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";

type SignalLabPulseProps = {
  data?: SignalPulseData;
  isLoading?: boolean;
  selectedItemId?: string | null;
  mobileTaskPanel?: "lab";
  onOpenLab: () => void;
  onSelect: (item: SignalPulseItem) => void;
};

export function SignalLabPulse({
  data,
  isLoading,
  selectedItemId,
  mobileTaskPanel,
  onOpenLab,
  onSelect,
}: SignalLabPulseProps) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const summary = data?.summary;
  return (
    <section className="compact-panel signal-lab-pulse" data-mobile-task-panel={mobileTaskPanel}>
      <header>
        <div>
          <FlaskConical aria-hidden />
          <h2>Signal Pulse</h2>
        </div>
        <button className="text-action" type="button" onClick={onOpenLab}>
          Open queue
        </button>
      </header>
      <div className="signal-attention-summary" aria-label="signal pulse summary">
        <SummaryPill label="trade" value={summary?.trade_candidate ?? 0} />
        <SummaryPill label="token" value={summary?.token_watch ?? 0} />
        <SummaryPill label="theme" value={summary?.theme_watch ?? 0} />
        <SummaryPill label="rejected" value={summary?.risk_rejected_high_info ?? 0} />
      </div>
      <SignalPulseList
        compact
        isLoading={isLoading}
        items={items}
        selectedItemId={selectedItemId}
        onSelect={onSelect}
      />
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

export function SignalPulseList({
  compact,
  isLoading,
  items,
  selectedItemId,
  onSelect,
}: SignalPulseListProps) {
  if (isLoading) {
    return <SkeletonRows compact={compact} count={compact ? 5 : 6} label="loading signal pulse" />;
  }
  if (!items.length) {
    return <RemoteState.Empty title="No pulse candidates in this window" />;
  }
  return (
    <div className={clsx("signal-chain-list", "signal-lab-pulse-list", compact && "compact")}>
      {items.map((item, index) => {
        const rowKey = itemKey(item, index);
        const view = buildPulseRowView(item);
        const venueActions = signalPulseVenueActions(item);
        return (
          <article
            className={clsx("signal-chain-row", selectedItemId === item.candidate_id && "selected")}
            key={rowKey}
          >
            <button
              aria-label={`open pulse case ${view.subjectTitle}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={clsx("signal-stage-badge", item.pulse_status)}>
                {view.stage}
              </span>
              <span className="signal-chain-main">
                <strong>{view.title}</strong>
                <em>{compact ? compactPulseMeta(view, item) : fullPulseMeta(view, item)}</em>
                <p>{view.summary}</p>
                <span className="signal-chain-chipline">
                  {view.facts.slice(0, compact ? 4 : 6).map((fact) => (
                    <span key={fact}>{fact}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{view.gate}</b>
                <small>{view.agent}</small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.updated_at_ms)}</span>
            </button>
            <span className="signal-lab-venue-links" data-signal-lab-action="venue">
              <Link aria-label={`Search Intel for ${view.title}`} className="venue-link" to={view.searchHref}>
                Search
              </Link>
              {venueActions.map((action) => (
                <a
                  aria-label={`Open ${view.subjectTitle.replace(/^\$+/, "")} on ${action.label}`}
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

function itemKey(item: SignalPulseItem, index: number): string {
  return item.candidate_id || item.target_id || item.subject_key || item.symbol || `pulse:${index}`;
}

type PulseRowView = {
  agent: string;
  facts: string[];
  gate: string;
  searchHref: string;
  stage: string;
  subjectTitle: string;
  summary: string;
  title: string;
};

function buildPulseRowView(item: SignalPulseItem): PulseRowView {
  const subject = item.factor_snapshot.subject;
  const symbol = subject.symbol ?? item.symbol ?? item.subject_key;
  const title = symbol ? `$${symbol.replace(/^\$+/, "")}` : item.candidate_id;
  const address = subject.address ?? subject.target_id ?? item.target_id;
  const facts = [
    factChip("Market cap", formatUsdCompact(numberValue(item.fact_card.market_cap_usd))),
    factChip("Liquidity", formatUsdCompact(numberValue(item.fact_card.liquidity_usd))),
    factChip("Holders", compactNumber(numberValue(item.fact_card.holders))),
    factChip("Volume 24h", formatUsdCompact(numberValue(item.fact_card.volume_24h_usd))),
    factChip("Mentions", compactNumber(numberValue(item.fact_card.mentions_1h))),
    factChip("Authors", compactNumber(numberValue(item.fact_card.unique_authors))),
  ].filter((value): value is string => Boolean(value));
  return {
    agent: item.decision.recommendation ?? "-",
    facts,
    gate: item.score_band ?? compactNumber(item.candidate_score),
    searchHref: searchPath({ q: symbol ? `$${symbol.replace(/^\$+/, "")}` : item.subject_key }),
    stage: statusLabel(item.pulse_status),
    subjectTitle: title,
    summary: item.decision.summary_zh || "Agent memo unavailable.",
    title: [title, subject.chain, shortAddress(address)].filter((value) => value && value !== "-").join(" · "),
  };
}

function fullPulseMeta(view: PulseRowView, item: SignalPulseItem): string {
  return [
    view.facts.slice(0, 3).join(" · "),
    `${view.stage} · ${view.gate}`,
    `updated ${formatRelativeTime(item.updated_at_ms)} ago`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function compactPulseMeta(view: PulseRowView, item: SignalPulseItem): string {
  const mentions = factChip("mentions", compactNumber(numberValue(item.fact_card.mentions_1h)));
  const authors = factChip("authors", compactNumber(numberValue(item.fact_card.unique_authors)));
  return [[mentions, authors].filter(Boolean).join(" · "), view.gate, `${formatRelativeTime(item.updated_at_ms)} ago`]
    .filter(Boolean)
    .join(" · ");
}

function factChip(label: string, value?: string): string | null {
  return value && value !== "-" ? `${label} ${value}` : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function statusLabel(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "-";
}
