import type { ReactNode } from "react";

import type { AgentRailView, DecisionSurfaceView, StageRailItem } from "../../model/pulseDetail";

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
      {agent.decisionSurface ? <DecisionSurfaceCard decision={agent.decisionSurface} /> : null}
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

function DecisionSurfaceCard({ decision }: { decision: DecisionSurfaceView }) {
  return (
    <section className={styles.decisionSurface} aria-label="v2 decision surface">
      <header>
        <h3>v2 决策</h3>
        <div className={styles.decisionMetrics}>
          <DecisionMetric label="route" value={decision.route} />
          <DecisionMetric label="rec" value={decision.recommendation} />
          <DecisionMetric label="conf" value={decision.confidenceLabel} />
        </div>
      </header>
      {decision.narrative ? (
        <div className={styles.narrative}>
          <strong>{decision.narrative.archetype}</strong>
          <p>{decision.narrative.thesis}</p>
        </div>
      ) : null}
      <div className={styles.decisionSides}>
        {decision.bull ? <DecisionSideBlock title="Bull" side={decision.bull} /> : null}
        {decision.bear ? <DecisionSideBlock title="Bear" side={decision.bear} /> : null}
      </div>
      {decision.playbook ? (
        <div className={styles.playbook}>
          <span>监控窗口 · {decision.playbook.monitoringHorizon}</span>
          <ListBlock title="观察信号" items={decision.playbook.watchSignals} />
          <ListBlock title="退出触发" items={decision.playbook.exitTriggers} />
        </div>
      ) : null}
      {decision.evidenceLinks.length ? (
        <div className={styles.evidenceLinks}>
          <h4>证据链接</h4>
          <ul>
            {decision.evidenceLinks.map((link) => (
              <li key={link.eventId}>
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.eventId}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function DecisionMetric({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <b>{label}</b>
      {value}
    </span>
  );
}

function DecisionSideBlock({
  side,
  title,
}: {
  side: NonNullable<DecisionSurfaceView["bull"]>;
  title: string;
}) {
  return (
    <div className={styles.decisionSide}>
      <h4>
        {title} · {side.strength}
      </h4>
      <p>{side.thesis}</p>
      {side.supportingEventIds.length ? (
        <p className={styles.eventIds}>{side.supportingEventIds.join(" · ")}</p>
      ) : null}
    </div>
  );
}

function ListBlock({ items, title }: { items: string[]; title: string }) {
  return (
    <div className={styles.listBlock}>
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className={styles.empty}>—</p>
      )}
    </div>
  );
}

function RailEntry({ item }: { item: StageRailItem }) {
  if (item.kind === "signal_analyst") {
    return (
      <StageCard title="阶段 1 · 信号分析" tone="info" status={item.status}>
        <SimpleBody summary={item.summary} latencyMs={item.latencyMs} />
      </StageCard>
    );
  }
  if (item.kind === "bear_case") {
    return (
      <StageCard title="阶段 2 · 反方风险" tone="warn" status={item.status}>
        <SimpleBody summary={item.summary} latencyMs={item.latencyMs} />
      </StageCard>
    );
  }
  if (item.kind === "risk_portfolio_judge") {
    return (
      <StageCard title="阶段 3 · 风险裁决" tone="agent" status={item.status}>
        <SimpleBody summary={item.summary} latencyMs={item.latencyMs} />
      </StageCard>
    );
  }
  return null;
}

function railKey(item: StageRailItem, index: number): string {
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
