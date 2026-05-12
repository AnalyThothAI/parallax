import type { SearchAgentBrief as SearchAgentBriefData } from "../api/types";

type SearchAgentBriefProps = {
  brief: SearchAgentBriefData;
};

export function SearchAgentBrief({ brief }: SearchAgentBriefProps) {
  return (
    <section className="search-agent-brief" aria-label="Agent Brief">
      <header>
        <h3>Agent Brief</h3>
        <span>{brief.schema_version}</span>
      </header>
      <div className="search-agent-grid">
        <article className="search-agent-card wide">
          <h4>项目总结</h4>
          <b>{brief.project_summary.one_liner}</b>
          <p>{brief.project_summary.summary_zh}</p>
          <EvidenceIds ids={brief.project_summary.evidence_event_ids} />
          {brief.project_summary.data_gaps.length ? (
            <ul>
              {brief.project_summary.data_gaps.map((gap) => (
                <li key={gap}>{gap}</li>
              ))}
            </ul>
          ) : null}
        </article>

        <article className="search-agent-card wide">
          <h4>传播</h4>
          <p>{brief.propagation.summary_zh}</p>
          <div className="search-agent-phase-list">
            {brief.propagation.phases.map((phase) => (
              <div key={`${phase.phase}:${phase.window_label}`}>
                <strong>{phase.phase}</strong>
                <span>
                  {phase.window_label} · {phase.tweets} tweets · {phase.authors} authors
                </span>
                <p>{phase.read_zh}</p>
                <em>{phase.lead_accounts.map((handle) => `@${handle}`).join(" · ")}</em>
                <EvidenceIds ids={phase.evidence_event_ids} />
              </div>
            ))}
          </div>
        </article>

        <article className="search-agent-card bull">
          <h4>多头观点</h4>
          <p>{brief.bull_bear.bull.thesis_zh}</p>
          <EvidenceIds ids={brief.bull_bear.bull.evidence_event_ids} />
          <ul>
            {brief.bull_bear.bull.triggers_zh.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>

        <article className="search-agent-card bear">
          <h4>空头观点</h4>
          <p>{brief.bull_bear.bear.thesis_zh}</p>
          <EvidenceIds ids={brief.bull_bear.bear.evidence_event_ids} />
          <ul>
            {brief.bull_bear.bear.invalidations_zh.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}

function EvidenceIds({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return (
    <div className="search-evidence-ids">
      {ids.map((id) => (
        <code key={id}>{id}</code>
      ))}
    </div>
  );
}
