import type { ReactNode } from "react";

import type { AgentRailView } from "../../model/pulseDetail";

import styles from "./PulseAgentRail.module.css";

type Props = {
  agent: AgentRailView;
};

export function PulseAgentRail({ agent }: Props) {
  return (
    <aside className={styles.rail} aria-label="agent reasoning">
      <header>
        <h2>Agent rail</h2>
        <p>
          {agent.model} · {agent.totalLatencyMs}ms
        </p>
      </header>
      {agent.mismatch ? (
        <section className={styles.mismatch}>
          <strong>Gate / agent mismatch</strong>
          <span>{agent.mismatch.gateLabel}</span>
          <span>{agent.mismatch.agentLabel}</span>
          <p>{agent.mismatch.note}</p>
        </section>
      ) : null}
      {agent.kind === "research_only" ? (
        <StageCard title="Research-only gate" status={agent.researchOnlyGate?.status ?? "skipped"}>
          <p>{agent.researchOnlyGate?.abstainReason || "no gate response"}</p>
        </StageCard>
      ) : (
        <>
          <StageCard title="Analyst" status={agent.analyst?.status ?? "skipped"}>
            <Metric label="confidence" value={agent.analyst?.confidence?.toFixed(2) ?? "n/a"} />
            <Metric label="recommendation" value={agent.analyst?.recommendation ?? "-"} />
            <p>{agent.analyst?.summary || "No analyst response."}</p>
            <BulletList items={agent.analyst?.evidence ?? []} />
          </StageCard>
          <StageCard title="Critic" status={agent.critic?.status ?? "skipped"}>
            <Metric label="ceiling" value={agent.critic?.confidenceCeiling?.toFixed(2) ?? "n/a"} />
            <Metric
              label="delta"
              value={
                agent.critic?.ceilingDeltaFromAnalyst != null
                  ? agent.critic.ceilingDeltaFromAnalyst.toFixed(2)
                  : "n/a"
              }
            />
            <BulletList items={agent.critic?.weaknesses ?? []} />
            <BulletList items={agent.critic?.missingFactImpacts ?? []} />
          </StageCard>
          <StageCard title="Judge" status={agent.judge?.status ?? "skipped"}>
            <Metric label="confidence" value={agent.judge?.confidence?.toFixed(2) ?? "n/a"} />
            <Metric label="recommendation" value={agent.judge?.recommendation ?? "-"} />
            <p>{agent.judge?.summary || "No judge response."}</p>
            <BulletList items={agent.judge?.residualRisks ?? []} />
            <BulletList items={agent.judge?.invalidationConditions ?? []} />
          </StageCard>
        </>
      )}
      <section className={styles.replay}>
        <h3>Replay</h3>
        <dl>
          <Meta label="pulse" value={agent.replay.pulseVersion} />
          <Meta label="gate" value={agent.replay.gateVersion} />
          <Meta label="prompt" value={agent.replay.promptVersion} />
          <Meta label="schema" value={agent.replay.schemaVersion} />
          <Meta label="run" value={agent.replay.runId} />
        </dl>
      </section>
    </aside>
  );
}

function StageCard({
  children,
  status,
  title,
}: {
  children: ReactNode;
  status: string;
  title: string;
}) {
  return (
    <section className={styles.stage} data-status={status}>
      <header>
        <h3>{title}</h3>
        <span>{status}</span>
      </header>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <dl className={styles.metric}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </dl>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <ul>
      {items.slice(0, 5).map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}
