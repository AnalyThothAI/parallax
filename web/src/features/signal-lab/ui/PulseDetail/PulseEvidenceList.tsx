import { useMemo, useState } from "react";

import type {
  EvidenceAuthorChip,
  EvidenceGroup,
  EvidenceRow,
  EvidenceView,
} from "../../model/pulseDetail";

import styles from "./PulseEvidenceList.module.css";

type Props = {
  evidence: EvidenceView;
};

type ViewTab = "all" | "cited";
type SortMode = "time_asc" | "time_desc" | "followers_desc";

export function PulseEvidenceList({ evidence }: Props) {
  const [view, setView] = useState<ViewTab>("all");
  const [handleFilter, setHandleFilter] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("time_asc");

  const filteredGroups = useMemo(() => {
    return evidence.groups
      .map((group) => filterGroup(group, view, handleFilter, sortMode))
      .filter((group) => group.rows.length > 0);
  }, [evidence.groups, view, handleFilter, sortMode]);

  return (
    <section className={styles.evidence} aria-label="source events">
      <header className={styles.head}>
        <div>
          <h2>Source events</h2>
          <p>
            {evidence.totalCount} events · {evidence.citedCount} cited ·{" "}
            {evidence.totalUniqueAuthors} authors
          </p>
        </div>
      </header>
      <div className={styles.toolbar}>
        <div className={styles.tabs}>
          <button
            type="button"
            data-active={view === "all" ? "true" : "false"}
            onClick={() => setView("all")}
          >
            All <em>{evidence.totalCount}</em>
          </button>
          <button
            type="button"
            data-active={view === "cited" ? "true" : "false"}
            disabled={evidence.citedCount === 0}
            onClick={() => setView("cited")}
          >
            ★ Cited <em>{evidence.citedCount}</em>
          </button>
        </div>
        <AuthorChips
          chips={evidence.authorChips}
          activeHandle={handleFilter}
          onToggle={(handle) =>
            setHandleFilter((current) => (current === handle ? null : handle))
          }
          totalUnique={evidence.totalUniqueAuthors}
        />
        <label className={styles.sort}>
          <span>sort</span>
          <select
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as SortMode)}
          >
            <option value="time_asc">time ↑</option>
            <option value="time_desc">time ↓</option>
            <option value="followers_desc">followers ↓</option>
          </select>
        </label>
      </div>
      {evidence.abstainCallout ? <p className={styles.callout}>{evidence.abstainCallout}</p> : null}
      <Concentration evidence={evidence} />
      <div className={styles.groups}>
        {filteredGroups.length === 0 ? (
          <p className={styles.empty}>No events match the current filters.</p>
        ) : (
          filteredGroups.map((group) => (
            <details key={group.id} open={group.defaultExpanded}>
              <summary>
                <span>{group.title}</span>
                <small>
                  {group.rows.length} events · {group.uniqueAuthors} authors · {group.rangeLabel}
                </small>
              </summary>
              <div className={styles.rows}>
                {group.rows.map((row) => (
                  <EvidenceRowItem key={row.eventId} row={row} />
                ))}
              </div>
            </details>
          ))
        )}
      </div>
    </section>
  );
}

function EvidenceRowItem({ row }: { row: EvidenceRow }) {
  return (
    <article data-cited={row.cited ? "true" : "false"} data-empty={row.isEmptyBody ? "true" : "false"}>
      <div className={styles.rowMeta}>
        {row.cited ? <span className={styles.star} aria-label="agent cited">★</span> : null}
        <strong>@{row.handle}</strong>
        <span data-tag={row.authorTag}>{row.authorTag.replaceAll("_", " ")}</span>
        {row.cohortPosition ? <span className={styles.position}>{row.cohortPosition}</span> : null}
        <time>{row.timestampLabel}</time>
      </div>
      <p>{row.body || "(empty repost / quote without captured body)"}</p>
      <small>
        {row.action} · {formatChannel(row.channel)}
        {row.followers != null ? ` · ${row.followers.toLocaleString()} followers` : ""}
      </small>
    </article>
  );
}

function AuthorChips({
  activeHandle,
  chips,
  onToggle,
  totalUnique,
}: {
  activeHandle: string | null;
  chips: EvidenceAuthorChip[];
  onToggle: (handle: string) => void;
  totalUnique: number;
}) {
  if (chips.length === 0) return null;
  return (
    <div className={styles.chips} aria-label="top authors">
      {chips.map((chip) => (
        <button
          key={chip.handle}
          type="button"
          data-tag={chip.authorTag}
          data-active={activeHandle === chip.handle ? "true" : "false"}
          onClick={() => onToggle(chip.handle)}
        >
          @{chip.handle} <em>{chip.postCount}</em>
        </button>
      ))}
      {totalUnique > chips.length ? (
        <span className={styles.chipMore}>+{totalUnique - chips.length} more</span>
      ) : null}
    </div>
  );
}

function Concentration({ evidence }: { evidence: EvidenceView }) {
  const segments = evidence.concentration.segments;
  if (segments.length === 0) return null;
  const total = segments.reduce((acc, segment) => acc + segment.count, 0);
  return (
    <section className={styles.concentrationWrap} aria-label="author concentration">
      <header>
        <span>Author concentration</span>
        <span>
          top author {Math.round(evidence.concentration.topAuthorShare * 100)}% · {segments.length}{" "}
          authors
        </span>
      </header>
      <div className={styles.concentrationBar}>
        {segments.map((segment) => (
          <span
            key={segment.handle}
            data-tone={segment.tone}
            style={{ flexGrow: Math.max(1, segment.count) }}
            title={`@${segment.handle}: ${segment.count} of ${total} (${Math.round(
              segment.share * 100,
            )}%)`}
          />
        ))}
      </div>
      <ul className={styles.concentrationLegend}>
        {segments.slice(0, 4).map((segment) => (
          <li key={segment.handle} data-tone={segment.tone}>
            <span aria-hidden />
            @{segment.handle} · {segment.count}/{total} ({Math.round(segment.share * 100)}%)
          </li>
        ))}
        {segments.length > 4 ? <li className={styles.legendMore}>+{segments.length - 4} more</li> : null}
      </ul>
    </section>
  );
}

function filterGroup(
  group: EvidenceGroup,
  view: ViewTab,
  handleFilter: string | null,
  sortMode: SortMode,
): EvidenceGroup {
  const rows = group.rows.filter((row) => {
    if (view === "cited" && !row.cited) return false;
    if (handleFilter && row.handle !== handleFilter) return false;
    return true;
  });
  const sorted = sortRows(rows, sortMode);
  return {
    ...group,
    rows: sorted,
    citedCount: sorted.filter((row) => row.cited).length,
    uniqueAuthors: new Set(sorted.map((row) => row.handle)).size,
  };
}

function sortRows(rows: EvidenceRow[], mode: SortMode): EvidenceRow[] {
  const next = [...rows];
  switch (mode) {
    case "time_asc":
      next.sort((a, b) => a.timestampMs - b.timestampMs);
      break;
    case "time_desc":
      next.sort((a, b) => b.timestampMs - a.timestampMs);
      break;
    case "followers_desc":
      next.sort((a, b) => (b.followers ?? -1) - (a.followers ?? -1));
      break;
  }
  return next;
}

function formatChannel(channel: string): string {
  switch (channel) {
    case "twitter_monitor_basic":
    case "twitter_monitor":
      return "Twitter";
    default:
      return channel.replaceAll("_", " ");
  }
}
