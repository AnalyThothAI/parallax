import { compactNumber, formatRelativeTime } from "@lib/format";
import type { SignalPulseData, SignalPulseItem } from "@lib/types";
import { RemoteState, SkeletonRows } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";

import { buildPulseCaseView, type PulseCaseView } from "../model/pulseCase";

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
    <div className={clsx("signal-chain-list", "signal-pulse-list", compact && "compact")}>
      {items.map((item, index) => {
        const rowKey = itemKey(item, index);
        const view = buildPulseCaseView(item);
        const facts = pulseFactChips(view);
        const venueActions = view.actions.filter((action) => action.kind === "venue");
        const searchAction = view.actions.find((action) => action.kind === "search");
        return (
          <article
            className={clsx("signal-chain-row", selectedItemId === item.candidate_id && "selected")}
            key={rowKey}
          >
            <button
              aria-label={`open pulse case ${view.subject.title}`}
              className="signal-chain-select"
              type="button"
              onClick={() => onSelect(item)}
            >
              <span className={clsx("signal-stage-badge", item.pulse_status)}>
                {view.stage.value}
              </span>
              <span className="signal-chain-main">
                <strong>{view.subject.title}</strong>
                <em>{compact ? compactPulseMeta(view, item) : fullPulseMeta(view, item)}</em>
                <p>{view.agentMemo.summary}</p>
                <span className="signal-chain-chipline">
                  {facts.slice(0, compact ? 4 : 6).map((fact) => (
                    <span key={fact}>{fact}</span>
                  ))}
                </span>
              </span>
              <span className="signal-chain-score">
                <b>{view.gate.value}</b>
                <small>{view.agentMemo.recommendation.value}</small>
              </span>
              <span className="signal-chain-time">{formatRelativeTime(item.updated_at_ms)}</span>
            </button>
            <span className="signal-pulse-venue-links" data-signal-pulse-action="venue">
              {searchAction ? (
                <Link
                  aria-label={`Search Intel for ${view.subject.title}`}
                  className="venue-link"
                  to={searchAction.href}
                >
                  {searchAction.label}
                </Link>
              ) : null}
              {venueActions.map((action) => (
                <a
                  aria-label={`Open ${actionSubject(view)} on ${action.label}`}
                  className="venue-link"
                  href={action.href}
                  key={`${action.label}:${action.href}`}
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

function fullPulseMeta(view: PulseCaseView, item: SignalPulseItem): string {
  return [
    marketFactMeta(view),
    socialFactMeta(view),
    `${view.stage.value} · ${view.gate.value}`,
    `updated ${formatRelativeTime(item.updated_at_ms)} ago`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function compactPulseMeta(view: PulseCaseView, item: SignalPulseItem): string {
  return [
    socialFactMeta(view),
    `${view.gate.value}`,
    `${formatRelativeTime(item.updated_at_ms)} ago`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function pulseFactChips(view: PulseCaseView): string[] {
  const ledger = new Map(view.factLedger.map((fact) => [fact.label, fact.value]));
  const community = parseCommunity(ledger.get("Community"));
  return [
    factChip("Market cap", ledger.get("Market cap")),
    factChip("Liquidity", ledger.get("Liquidity")),
    factChip("Holders", ledger.get("Holders")),
    factChip("Volume 24h", ledger.get("Volume 24h")),
    community.mentions,
    community.authors,
  ].filter((value): value is string => Boolean(value));
}

function marketFactMeta(view: PulseCaseView): string | null {
  const ledger = new Map(view.factLedger.map((fact) => [fact.label, fact.value]));
  return (
    [
      factChip("Market cap", ledger.get("Market cap")),
      factChip("Liquidity", ledger.get("Liquidity")),
      factChip("Holders", ledger.get("Holders")),
    ]
      .filter(Boolean)
      .join(" · ") || null
  );
}

function socialFactMeta(view: PulseCaseView): string | null {
  const community = parseCommunity(
    view.factLedger.find((fact) => fact.label === "Community")?.value,
  );
  return [community.mentions, community.authors].filter(Boolean).join(" · ") || null;
}

function factChip(label: string, value?: string): string | null {
  return value && value !== "-" ? `${label} ${value}` : null;
}

function parseCommunity(value?: string): { authors: string | null; mentions: string | null } {
  const [posts, authors] = value?.split(" · ") ?? [];
  return {
    authors: authors?.replace(" authors", "") ? `authors ${authors.replace(" authors", "")}` : null,
    mentions: posts?.replace(" posts", "") ? `mentions ${posts.replace(" posts", "")}` : null,
  };
}

function actionSubject(view: PulseCaseView): string {
  return view.subject.title.replace(/^\$+/, "");
}
