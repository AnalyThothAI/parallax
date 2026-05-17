import type { ReactNode } from "react";

import type { AgentRailView, StageRailItem } from "../../model/pulseDetail";

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
        {agent.isLegacy ? (
          <p className={styles.legacyNotice} data-testid="legacy-stage-notice">
            此运行为旧版三阶段（analyst/critic/judge）数据，仅展示占位卡
          </p>
        ) : null}
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
          <Metric label="弃判原因" value={agent.researchOnlyGate?.abstainReason || "—"} />
        </StageCard>
      ) : (
        <>
          {agent.railItems.map((item, index) => (
            <RailEntry key={railKey(item, index)} item={item} />
          ))}
          {agent.railItems.length === 0 ? (
            <p className={styles.skipped}>（暂无 stage 数据）</p>
          ) : null}
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

function RailEntry({ item }: { item: StageRailItem }) {
  if (item.kind === "investigator") {
    return (
      <StageCard title="阶段 1 · 调研" tone="info" status={item.status}>
        <SimpleBody summary={item.summary} latencyMs={item.latencyMs} />
      </StageCard>
    );
  }
  if (item.kind === "decision_maker") {
    return (
      <StageCard title="阶段 2 · 决策" tone="agent" status={item.status}>
        <SimpleBody summary={item.summary} latencyMs={item.latencyMs} />
      </StageCard>
    );
  }
  return (
    <StageCard
      title={`Legacy · ${item.stageName}`}
      tone="neutral"
      status={item.status}
      subtitle="历史 v1 数据"
    >
      <LegacyBody summary={item.summary} latencyMs={item.latencyMs} />
    </StageCard>
  );
}

function railKey(item: StageRailItem, index: number): string {
  if (item.kind === "legacy") return `legacy-${item.stageName}-${index}`;
  return `${item.kind}-${index}`;
}

function SimpleBody({ summary, latencyMs }: { summary: string; latencyMs: number | null }) {
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="耗时" value={formatLatency(latencyMs)} tone="info" />
      </div>
      <p>{summary || "—"}</p>
    </>
  );
}

function LegacyBody({ summary, latencyMs }: { summary: string; latencyMs: number | null }) {
  return (
    <>
      <div className={styles.kpis}>
        <Metric label="耗时" value={formatLatency(latencyMs)} tone="neutral" />
      </div>
      <p>{summary || "—"}</p>
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
  label,
  tone = "neutral",
  value,
}: {
  label: string;
  tone?: "info" | "warn" | "risk" | "agent" | "neutral";
  value: string;
}) {
  return (
    <dl className={styles.metric} data-tone={tone}>
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

function formatLatency(value: number | null): string {
  if (value == null) return "—";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function formatSeconds(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
