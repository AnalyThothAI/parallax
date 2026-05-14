import type { ReactNode } from "react";

import type { AgentRailView, AnalystView, CriticView, JudgeView } from "../../model/pulseDetail";

import styles from "./PulseAgentRail.module.css";

type Props = {
  agent: AgentRailView;
};

export function PulseAgentRail({ agent }: Props) {
  return (
    <aside className={styles.rail} aria-label="agent reasoning">
      <header>
        <h2>Agent 推理栏</h2>
        <p>
          {agent.model} · 总耗时 {formatSeconds(agent.totalLatencyMs)}
        </p>
      </header>
      {agent.mismatch ? (
        <section className={styles.mismatch}>
          <strong>策略门与 Agent 失谐</strong>
          <span>{agent.mismatch.gateLabel}</span>
          <span>{agent.mismatch.agentLabel}</span>
          <p>{agent.mismatch.note}</p>
        </section>
      ) : null}
      {agent.kind === "research_only" ? (
        <StageCard
          title="预 LLM 门控"
          subtitle="确定性"
          status={agent.researchOnlyGate?.status ?? "skipped"}
        >
          <Metric label="弃判原因" value={agent.researchOnlyGate?.abstainReason || "（未设置）"} />
        </StageCard>
      ) : (
        <>
          <StageCard title="阶段 1 · 分析" tone="info" status={agent.analyst?.status ?? "skipped"}>
            <AnalystBody analyst={agent.analyst} />
          </StageCard>
          <StageCard title="阶段 2 · 评审" tone="warn" status={agent.critic?.status ?? "skipped"}>
            <CriticBody critic={agent.critic} />
          </StageCard>
          <StageCard title="阶段 3 · 终裁" tone="agent" status={agent.judge?.status ?? "skipped"}>
            <JudgeBody judge={agent.judge} />
          </StageCard>
        </>
      )}
      <details className={styles.replay}>
        <summary>回放 · 版本 · 原始载荷</summary>
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
    return <p className={styles.skipped}>（阶段被跳过或不可用）</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="建议" value={analyst.recommendation} />
        <Metric label="置信度" value={formatConf(analyst.confidence)} tone="info" />
      </div>
      <p>{analyst.summary || "（无摘要）"}</p>
      <BulletGroup
        label={`论据 (${analyst.evidence.length})`}
        items={analyst.evidence}
        tone="neutral"
      />
    </>
  );
}

function CriticBody({ critic }: { critic: CriticView }) {
  if (!critic) {
    return <p className={styles.skipped}>（阶段被跳过或不可用）</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric
          label="是否弃判"
          value={critic.shouldAbstain ? "是" : "否"}
          tone={critic.shouldAbstain ? "risk" : "neutral"}
        />
        <Metric
          label="置信度上限"
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
        label={`Critic 列出的弱点 (${critic.weaknesses.length})`}
        items={critic.weaknesses}
        tone="warn"
      />
      <BulletGroup
        label={`缺数据影响 (${critic.missingFactImpacts.length})`}
        items={critic.missingFactImpacts}
        tone="risk"
      />
    </>
  );
}

function JudgeBody({ judge }: { judge: JudgeView }) {
  if (!judge) {
    return <p className={styles.skipped}>（阶段被跳过或不可用）</p>;
  }
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="路由" value={judge.route} tone="info" />
        <Metric label="建议" value={judge.recommendation} tone="agent" />
        <Metric
          label="置信度"
          value={formatConf(judge.confidence)}
          delta={judge.belowCeiling ? "低于 Critic 上限" : null}
          tone="risk"
        />
        <Metric
          label="弃判原因"
          value={judge.abstainReason ?? "—"}
          tone={judge.abstainReason ? "warn" : "neutral"}
        />
      </div>
      <p>{judge.summary || "（无摘要）"}</p>
      <BulletGroup
        label={`残留风险 (${judge.residualRisks.length})`}
        items={judge.residualRisks}
        tone="risk"
      />
      <BulletGroup
        label={`失效条件 (${judge.invalidationConditions.length})`}
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
    return <p className={styles.empty}>{label} · （无条目）</p>;
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
