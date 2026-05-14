import type { PulseDetailViewModel } from "../../model/pulseDetail";

import styles from "./PulseEvidenceList.module.css";

type Props = {
  evidence: PulseDetailViewModel["evidence"];
};

export function PulseEvidenceList({ evidence }: Props) {
  return (
    <section className={styles.evidence} aria-label="source events">
      <header>
        <div>
          <h2>Source events</h2>
          <p>
            {evidence.totalCount} events · {evidence.citedCount} cited ·{" "}
            {evidence.totalUniqueAuthors} authors
          </p>
        </div>
        <AuthorChips evidence={evidence} />
      </header>
      <Concentration evidence={evidence} />
      {evidence.abstainCallout ? <p className={styles.callout}>{evidence.abstainCallout}</p> : null}
      <div className={styles.groups}>
        {evidence.groups.map((group) => (
          <details key={group.id} open={group.defaultExpanded}>
            <summary>
              <span>{group.title}</span>
              <small>
                {group.rows.length} events · {group.uniqueAuthors} authors · {group.rangeLabel}
              </small>
            </summary>
            <div className={styles.rows}>
              {group.rows.map((row) => (
                <article key={row.eventId} data-cited={row.cited ? "true" : "false"}>
                  <div className={styles.rowMeta}>
                    <strong>@{row.handle}</strong>
                    <span data-tag={row.authorTag}>{row.authorTag.replaceAll("_", " ")}</span>
                    {row.cohortPosition ? <span>{row.cohortPosition}</span> : null}
                    <time>{row.timestampLabel}</time>
                  </div>
                  <p>{row.body || "repost / quote with no captured text"}</p>
                  <small>
                    {row.action} · {row.channel}
                    {row.followers != null ? ` · ${row.followers.toLocaleString()} followers` : ""}
                  </small>
                </article>
              ))}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function AuthorChips({ evidence }: Props) {
  if (!evidence.authorChips.length) {
    return null;
  }
  return (
    <div className={styles.chips} aria-label="top authors">
      {evidence.authorChips.map((chip) => (
        <span key={chip.handle} data-tag={chip.authorTag}>
          @{chip.handle} · {chip.postCount}
        </span>
      ))}
    </div>
  );
}

function Concentration({ evidence }: Props) {
  if (!evidence.concentration.segments.length) {
    return null;
  }
  return (
    <div className={styles.concentration} aria-label="author concentration">
      {evidence.concentration.segments.map((segment) => (
        <span
          key={segment.handle}
          data-tone={segment.tone}
          style={{ flexGrow: Math.max(1, segment.count), flexBasis: `${segment.share * 100}%` }}
          title={`@${segment.handle}: ${Math.round(segment.share * 100)}%`}
        />
      ))}
    </div>
  );
}
