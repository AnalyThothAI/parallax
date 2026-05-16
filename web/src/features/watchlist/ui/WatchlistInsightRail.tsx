import type { WatchlistOverviewCluster } from "@lib/types";
import { searchPath } from "@shared/routing/paths";
import { RemoteState } from "@shared/ui/RemoteState";
import { Link } from "react-router-dom";

export function WatchlistInsightRail({
  candidateClusters,
  narrativeClusters,
  resolvedClusters,
  riskNotes,
}: {
  candidateClusters: WatchlistOverviewCluster[];
  narrativeClusters: WatchlistOverviewCluster[];
  resolvedClusters: WatchlistOverviewCluster[];
  riskNotes: string[];
}) {
  return (
    <aside className="watchlist-extraction-panel" aria-label="Extracted account signals">
      <ClusterPanel
        emptyLabel="No resolved token targets in this window."
        eyebrow="token projection"
        items={resolvedClusters}
        title="Resolved targets"
      />
      <ClusterPanel
        emptyLabel="No unresolved candidate mentions in this window."
        eyebrow="extracted candidates"
        items={candidateClusters}
        title="Candidate mentions"
      />
      <ClusterPanel
        emptyLabel="No narrative clusters in this window."
        eyebrow="hashtags"
        items={narrativeClusters}
        title="Narrative clusters"
      />
      <RiskPanel notes={riskNotes} />
    </aside>
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
  items: WatchlistOverviewCluster[];
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
  items: WatchlistOverviewCluster[];
}) {
  if (!items.length) {
    return <RemoteState.Empty title={emptyLabel} />;
  }

  return (
    <ul className="watchlist-cluster-list">
      {items.map((item) => (
        <li key={`${item.kind}-${item.label}`}>
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

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
