import type { ReactNode } from "react";

import type {
  AgentRailView,
  AnalystView,
  CriticView,
  JudgeView,
} from "../../model/pulseDetail";

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
          {agent.model} · {formatSeconds(agent.totalLatencyMs)}
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
        <StageCard
          title="pre-LLM gate"
          subtitle="deterministic"
          status={agent.researchOnlyGate?.status ?? "skipped"}
        >
          <Metric
            label="abstain_reason"
            value={agent.researchOnlyGate?.abstainReason || "(unset)"}
          />
        </StageCard>
      ) : (
        <>
          <StageCard
            title="stage 1 · analyst"
            tone="info"
            status={agent.analyst?.status ?? "skipped"}
          >
            <AnalystBody analyst={agent.analyst} />
          </StageCard>
          <StageCard
            title="stage 2 · critic"
            tone="warn"
            status={agent.critic?.status ?? "skipped"}
          >
            <CriticBody critic={agent.critic} />
          </StageCard>
          <StageCard
            title="stage 3 · judge · final"
            tone="agent"
            status={agent.judge?.status ?? "skipped"}
          >
            <JudgeBody judge={agent.judge} />
          </StageCard>
        </>
      )}
      <details className={styles.replay}>
        <summary>Replay · versions · raw payloads</summary>
        <dl>
          <Meta label="pulse" value={agent.replay.pulseVersion} />
          <Meta label="gate" value={agent.replay.gateVersion} />
          <Meta label="prompt" value={agent.replay.promptVersion} />
          <Meta label="schema" value={agent.replay.schemaVersion} />
          <Meta label="run" value={agent.replay.runId} />
          <Meta label="candidate" value={agent.replay.candidateId} />
        </dl>
      </details>
    </aside>
  );
}

function AnalystBody({ analyst }: { analyst: AnalystView }) {
  if (!analyst) {
    return <p className={styles.skipped}>(stage skipped or unavailable)</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="recommendation" value={analyst.recommendation} />
        <Metric
          label="confidence"
          value={formatConf(analyst.confidence)}
          tone="info"
        />
      </div>
      <p>{analyst.summary || "(no summary)"}</p>
      <BulletGroup
        label={`evidence (${analyst.evidence.length})`}
        items={analyst.evidence}
        tone="neutral"
      />
    </>
  );
}

function CriticBody({ critic }: { critic: CriticView }) {
  if (!critic) {
    return <p className={styles.skipped}>(stage skipped or unavailable)</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric
          label="should_abstain"
          value={critic.shouldAbstain ? "true" : "false"}
          tone={critic.shouldAbstain ? "risk" : "neutral"}
        />
        <Metric
          label="confidence ceiling"
          value={formatConf(critic.confidenceCeiling)}
          delta={
            critic.ceilingDeltaFromAnalyst != null
              ? formatDelta(critic.ceilingDeltaFromAnalyst)
              : null
          }
          tone="warn"
        />
      </div>
      <BulletGroup
        label={`weaknesses (${critic.weaknesses.length})`}
        items={critic.weaknesses}
        tone="warn"
      />
      <BulletGroup
        label={`missing fact impacts (${critic.missingFactImpacts.length})`}
        items={critic.missingFactImpacts}
        tone="risk"
      />
    </>
  );
}

function JudgeBody({ judge }: { judge: JudgeView }) {
  if (!judge) {
    return <p className={styles.skipped}>(stage skipped or unavailable)</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="route" value={judge.route} tone="info" />
        <Metric label="recommendation" value={judge.recommendation} tone="agent" />
        <Metric
          label="confidence"
          value={formatConf(judge.confidence)}
          delta={judge.belowCeiling ? "under ceiling" : null}
          tone="risk"
        />
        <Metric
          label="abstain_reason"
          value={judge.abstainReason ?? "null"}
          tone={judge.abstainReason ? "warn" : "neutral"}
        />
      </div>
      <p>{judge.summary || "(no summary)"}</p>
      <BulletGroup
        label={`residual risks (${judge.residualRisks.length})`}
        items={judge.residualRisks}
        tone="risk"
      />
      <BulletGroup
        label={`invalidation conditions (${judge.invalidationConditions.length})`}
        items={judge.invalidationConditions}
        tone="warn"
      />
    </>
  );
}

function StageCard({
  children,
  status,
  subtitle,
  title,
  tone = "neutral",
}: {
  children: ReactNode;
  status: string;
  subtitle?: string;
  title: string;
  tone?: "info" | "warn" | "agent" | "neutral";
}) {
  return (
    <section className={styles.stage} data-status={status} data-tone={tone}>
      <header>
        <h3>{title}</h3>
        <span>
          {subtitle ? `${subtitle} · ` : ""}
          {status}
        </span>
      </header>
      {children}
    </section>
  );
}

function Metric({
  delta,
  label,
  tone = "neutral",
  value,
}: {
  delta?: string | null;
  label: string;
  tone?: "info" | "warn" | "risk" | "agent" | "neutral";
  value: string;
}) {
  return (
    <dl className={styles.metric} data-tone={tone}>
      <dt>{label}</dt>
      <dd>
        {value}
        {delta ? <small> · {delta}</small> : null}
      </dd>
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

function BulletGroup({
  items,
  label,
  tone,
}: {
  items: string[];
  label: string;
  tone: "warn" | "risk" | "neutral";
}) {
  if (!items.length) {
    return <p className={styles.empty}>{label} · (no entries)</p>;
  }
  return (
    <section className={styles.bullets} data-tone={tone}>
      <h4>{label}</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function formatConf(value: number | null): string {
  if (value === null) return "n/a";
  return value.toFixed(2);
}

function formatDelta(value: number): string {
  const sign = value > 0 ? "↑" : "↓";
  return `${sign} ${Math.abs(value).toFixed(2)}`;
}

function formatSeconds(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
