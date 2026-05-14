import { formatRelativeTime } from "@lib/format";
import { searchPath } from "@shared/routing/paths";
import { RemoteState } from "@shared/ui/RemoteState";
import { ObsidianPill } from "@shared/ui/case-file";
import { AtSign, ExternalLink, Radio, Search } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { WatchlistAccountCase } from "../model/watchlistCase";
import { normalizeWatchlistHandle } from "../model/watchlistCase";

type WatchlistPageProps = {
  accountCases: WatchlistAccountCase[];
};

export function WatchlistPage({ accountCases }: WatchlistPageProps) {
  const [searchParams] = useSearchParams();
  const selectedHandle =
    normalizeWatchlistHandle(searchParams.get("handle")) ?? accountCases[0]?.handle ?? null;
  const selectedCase =
    accountCases.find((item) => item.handle === selectedHandle) ??
    (selectedHandle ? emptyAccountCase(selectedHandle) : null);

  if (!selectedCase) {
    return (
      <section className="watchlist-page" aria-label="Watchlist">
        <RemoteState.Empty title="No watchlist handles configured." />
      </section>
    );
  }

  return (
    <section className="watchlist-page" aria-label="Twitter source monitor">
      <div className="watchlist-monitor-shell">
        <WatchlistHero selectedCase={selectedCase} />
        <SignalStrip selectedCase={selectedCase} />
        <div className="watchlist-monitor-grid">
          <section className="watchlist-evidence-panel" aria-labelledby="watchlist-evidence-title">
            <div className="watchlist-section-head">
              <span>source events</span>
              <h3 id="watchlist-evidence-title">Recent evidence</h3>
              <p>{selectedCase.emptyState ?? "Latest events from the monitored account."}</p>
            </div>
            <EvidenceStream selectedCase={selectedCase} />
          </section>

          <aside className="watchlist-extraction-panel" aria-label="Extracted account signals">
            <ClusterPanel
              emptyLabel="No token mentions in this window."
              eyebrow="extracted targets"
              items={selectedCase.tokenMentions}
              title="Token mentions"
            />
            <ClusterPanel
              emptyLabel="No narrative clusters in this window."
              eyebrow="hashtags"
              items={selectedCase.narrativeClusters}
              title="Narrative clusters"
            />
            <RiskPanel notes={selectedCase.riskNotes} />
          </aside>
        </div>
      </div>
    </section>
  );
}

function WatchlistHero({ selectedCase }: { selectedCase: WatchlistAccountCase }) {
  return (
    <header className="watchlist-monitor-hero">
      <div className="watchlist-source-mark" aria-hidden>
        <AtSign />
      </div>
      <div className="watchlist-monitor-title">
        <span className="watchlist-kicker">
          <Radio aria-hidden />
          source monitor
        </span>
        <h2>@{selectedCase.handle}</h2>
        <p>{lastSeenCopy(selectedCase.lastSeenAtMs)}</p>
      </div>
      <div className="watchlist-monitor-actions" aria-label="Account actions">
        {selectedCase.searchLinks.map((link) => (
          <Link className="watchlist-action primary" key={link.href} to={link.href}>
            <Search aria-hidden />
            {link.label}
          </Link>
        ))}
        <a
          className="watchlist-action"
          href={`https://x.com/${selectedCase.handle}`}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink aria-hidden />
          Open X
        </a>
      </div>
    </header>
  );
}

function SignalStrip({ selectedCase }: { selectedCase: WatchlistAccountCase }) {
  return (
    <section className="watchlist-signal-strip" aria-label="Monitor status">
      <SignalCard
        detail={selectedCase.unreadCount ? "notifications waiting" : "queue clear"}
        label="Unread"
        tone={selectedCase.unreadCount ? "opportunity" : "neutral"}
        value={selectedCase.unreadCount}
      />
      <SignalCard
        detail={selectedCase.emptyState ?? "captured from public stream"}
        label="Evidence"
        tone={selectedCase.recentEvents.length ? "health" : "neutral"}
        value={selectedCase.recentEvents.length}
      />
      <SignalCard
        detail={topClusterCopy(selectedCase.tokenMentions)}
        label="Tokens"
        tone={selectedCase.tokenMentions.length ? "info" : "neutral"}
        value={selectedCase.tokenMentions.length}
      />
      <SignalCard
        detail={topClusterCopy(selectedCase.narrativeClusters)}
        label="Narratives"
        tone={selectedCase.narrativeClusters.length ? "agent" : "neutral"}
        value={selectedCase.narrativeClusters.length}
      />
    </section>
  );
}

function SignalCard({
  detail,
  label,
  tone,
  value,
}: {
  detail: ReactNode;
  label: string;
  tone: "agent" | "health" | "info" | "neutral" | "opportunity";
  value: ReactNode;
}) {
  return (
    <article className={`watchlist-signal-card ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      <p>{detail}</p>
    </article>
  );
}

function EvidenceStream({ selectedCase }: { selectedCase: WatchlistAccountCase }) {
  if (!selectedCase.recentEvents.length) {
    return <RemoteState.Empty title={selectedCase.emptyState ?? "No recent evidence."} />;
  }

  return (
    <ol className="watchlist-evidence-stream">
      {selectedCase.recentEvents.map((item) => (
        <li key={item.id}>
          <div className="watchlist-evidence-time">
            <span>{item.meta}</span>
          </div>
          <article className="watchlist-evidence-card">
            <div>
              {item.href ? (
                <a href={item.href} rel="noreferrer" target="_blank">
                  {item.title}
                </a>
              ) : (
                <b>{item.title}</b>
              )}
              <ObsidianPill tone="health">source</ObsidianPill>
            </div>
            <p>{item.body}</p>
          </article>
        </li>
      ))}
    </ol>
  );
}

function ClusterPanel({
  emptyLabel,
  eyebrow,
  items,
  title,
}: {
  emptyLabel: string;
  eyebrow: string;
  items: WatchlistAccountCase["tokenMentions"];
  title: string;
}) {
  return (
    <section className="watchlist-cluster-panel" aria-labelledby={`watchlist-${slug(title)}`}>
      <div className="watchlist-section-head">
        <span>{eyebrow}</span>
        <h3 id={`watchlist-${slug(title)}`}>{title}</h3>
      </div>
      <ClusterList emptyLabel={emptyLabel} items={items} />
    </section>
  );
}

function ClusterList({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: WatchlistAccountCase["tokenMentions"];
}) {
  if (!items.length) {
    return <RemoteState.Empty title={emptyLabel} />;
  }

  return (
    <ul className="watchlist-cluster-list">
      {items.map((item) => (
        <li key={item.label}>
          <Link to={searchPath({ q: item.query })}>
            <b>{item.label}</b>
            <span>
              {item.count} event{item.count === 1 ? "" : "s"}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RiskPanel({ notes }: { notes: string[] }) {
  return (
    <section className="watchlist-cluster-panel" aria-labelledby="watchlist-risk-notes">
      <div className="watchlist-section-head">
        <span>data quality</span>
        <h3 id="watchlist-risk-notes">Risk notes</h3>
      </div>
      {notes.length ? (
        <ul className="watchlist-risk-list">
          {notes.map((note, index) => (
            <li key={`${note}-${index}`}>{note}</li>
          ))}
        </ul>
      ) : (
        <RemoteState.Empty title="No account-level risk notes in this window." />
      )}
    </section>
  );
}

function emptyAccountCase(handle: string): WatchlistAccountCase {
  return {
    emptyState: "No source events in this window.",
    handle,
    lastSeenAtMs: null,
    narrativeClusters: [],
    recentEvents: [],
    riskNotes: [],
    searchLinks: [
      {
        href: searchPath({ q: `@${handle}` }),
        label: "Search account",
      },
    ],
    tokenMentions: [],
    unreadCount: 0,
  };
}

function lastSeenCopy(value: number | null): string {
  return value ? `Last source event ${formatRelativeTime(value)} ago` : "No recent source event";
}

function topClusterCopy(items: WatchlistAccountCase["tokenMentions"]): string {
  const [top] = items;
  return top ? `lead ${top.label} · ${top.count} event${top.count === 1 ? "" : "s"}` : "none yet";
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
