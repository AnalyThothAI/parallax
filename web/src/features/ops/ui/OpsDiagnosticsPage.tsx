import { formatRelativeTime } from "@lib/format";
import * as PageState from "@shared/ui/PageState";
import clsx from "clsx";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Database,
  ListChecks,
  RadioTower,
  ServerCog,
  Workflow,
} from "lucide-react";

import {
  domainRows,
  requireOpsDiagnostics,
  requireOpsQueueData,
  statusRank,
  statusTone,
  type OpsAgentExecution,
  type OpsDiagnostics,
  type OpsJson,
  type OpsProvider,
  type OpsQueueData,
  type OpsQueueItem,
  type OpsQueueSummary,
  type OpsSectionStatus,
  type OpsWorker,
} from "../model/opsDiagnostics";
import "./ops.css";
import "./opsQueues.css";

type OpsDiagnosticsPageProps = {
  diagnostics: OpsDiagnostics | null | undefined;
  error?: unknown;
  loading: boolean;
  queue: OpsQueueData | null | undefined;
  queueLoading?: boolean;
  selectedQueueName: string | null;
  onRefresh?: () => void;
  onSelectQueue: (queueName: string) => void;
};

type ChainLane = {
  title: string;
  status: OpsSectionStatus;
  intent: string;
  primary: string;
  secondary: string;
  icon: "activity" | "database" | "workflow" | "server" | "list";
};

export function OpsDiagnosticsPage({
  diagnostics,
  error,
  loading,
  queue,
  queueLoading = false,
  selectedQueueName,
  onRefresh,
  onSelectQueue,
}: OpsDiagnosticsPageProps) {
  if (loading) {
    return <PageState.Loading label="加载运维诊断" layout="route" rows={6} />;
  }
  if (error) {
    return <PageState.Error error={error} onRetry={onRefresh} />;
  }
  if (!diagnostics) {
    return <PageState.Error error={new Error("ops_current_contract:diagnostics_required")} />;
  }

  let currentDiagnostics: OpsDiagnostics;
  try {
    currentDiagnostics = requireOpsDiagnostics(diagnostics);
  } catch (contractError) {
    return <PageState.Error error={contractError} onRetry={onRefresh} />;
  }

  const incidents = incidentRows(currentDiagnostics);
  const chain = runtimeChain(currentDiagnostics);
  const providersByStatus = sortByAttention(currentDiagnostics.providers);
  const workersByStatus = sortByAttention(currentDiagnostics.workers);
  const rows = domainRows(currentDiagnostics);
  const overall = statusTone(currentDiagnostics.overall.status);

  return (
    <main className="ops-page ops-page-v2">
      <header className={clsx("ops-command", `is-${overall}`)}>
        <div className="ops-command-copy">
          <p className="ops-kicker">运维 / 控制面</p>
          <h1>运维诊断</h1>
          <p>
            按链路查看从实时输入到决策输出的运行状态。事实表和读模型是业务真相；队列和 Provider
            用来解释新鲜度。
          </p>
        </div>
        <div className="ops-command-status">
          <StatusChip status={overall} />
          <span>{`${relativeTimeLabel(currentDiagnostics.generated_at_ms)}前`}</span>
        </div>
      </header>

      <section className="ops-command-grid">
        <section className="ops-panel ops-incident-panel" aria-labelledby="ops-incident-board">
          <SectionHeader
            title="故障看板"
            detail={incidentSummary(currentDiagnostics, incidents.length)}
            id="ops-incident-board"
          />
          <div className="ops-incident-list">
            {incidents.length ? (
              incidents.map((incident) => (
                <div className={clsx("ops-incident", `is-${incident.status}`)} key={incident.id}>
                  <StatusIcon status={incident.status} />
                  <div>
                    <b>{incident.title}</b>
                    <span>{incident.detail}</span>
                  </div>
                </div>
              ))
            ) : overall === "ok" ? (
              <div className="ops-incident is-ok">
                <CheckCircle2 aria-hidden />
                <div>
                  <b>没有阻塞项</b>
                  <span>当前暴露的模块均为正常、空闲或停用状态。</span>
                </div>
              </div>
            ) : (
              <div className="ops-incident is-unknown">
                <ServerCog aria-hidden />
                <div>
                  <b>诊断未定位到具体阻塞项</b>
                  <span>
                    {currentDiagnostics.overall.reasons[0] ?? "整体状态并非正常，请检查原始诊断。"}
                  </span>
                </div>
              </div>
            )}
          </div>
          <div className="ops-check-row">
            <span>建议检查 {currentDiagnostics.suggested_checks.length} 项</span>
            {currentDiagnostics.suggested_checks.slice(0, 3).map((check) => (
              <code key={String(check.id ?? check.label)}>{String(check.label ?? check.id)}</code>
            ))}
          </div>
        </section>

        <section className="ops-panel ops-live-panel" aria-labelledby="ops-live-input">
          <SectionHeader title="实时输入" detail="采集计数" id="ops-live-input" />
          <CollectorSnapshot diagnostics={currentDiagnostics} />
        </section>
      </section>

      <section className="ops-panel" aria-labelledby="ops-runtime-chain">
        <SectionHeader title="运行链路" detail="信号卡在哪一段" id="ops-runtime-chain" />
        <div className="ops-chain">
          {chain.map((lane) => (
            <ChainCard key={lane.title} lane={lane} />
          ))}
        </div>
      </section>

      <section className="ops-grid">
        <section className="ops-panel" aria-labelledby="ops-domain-readiness">
          <SectionHeader title="业务域就绪" detail="公开读路径" id="ops-domain-readiness" />
          <div className="ops-domain-list">
            {rows.map((row) => (
              <div className="ops-domain-row" key={row.name}>
                <span>
                  <b>{domainLabel(row.name)}</b>
                  <small>{row.reason}</small>
                </span>
                <StatusChip status={row.status} />
                <em>积压 {row.backlog}</em>
              </div>
            ))}
          </div>
        </section>

        <section className="ops-panel" aria-labelledby="ops-worker-fleet">
          <SectionHeader
            title="Worker 状态"
            detail={`${currentDiagnostics.workers.length} 个 Worker / ${currentDiagnostics.providers.length} 个 Provider`}
            id="ops-worker-fleet"
          />
          <div className="ops-fleet">
            <div>
              <h3>Provider 输入输出</h3>
              {providersByStatus.map((provider) => (
                <ProviderRow key={`${provider.domain}:${provider.provider}`} provider={provider} />
              ))}
            </div>
            <div>
              <h3>运行中 Worker</h3>
              {workersByStatus.slice(0, 14).map((worker) => (
                <WorkerRow key={worker.name} worker={worker} />
              ))}
            </div>
          </div>
        </section>
      </section>

      <section className="ops-panel" aria-labelledby="ops-queue-inspector">
        <SectionHeader
          title="队列排查"
          detail={`${currentDiagnostics.queues.length} 个允许查看的队列`}
          id="ops-queue-inspector"
        />
        <div className="ops-queue-layout">
          <div className="ops-queue-list" aria-label="任务队列">
            {sortByAttention(currentDiagnostics.queues).map((item) => (
              <QueueButton
                active={item.queue_name === selectedQueueName}
                key={item.queue_name}
                queue={item}
                onSelectQueue={onSelectQueue}
              />
            ))}
          </div>
          <QueueDetail loading={queueLoading} queue={queue} selectedQueueName={selectedQueueName} />
        </div>
      </section>

      <section className="ops-panel ops-config" aria-labelledby="ops-runtime-config">
        <SectionHeader title="运行配置" detail="仅显示路径和配置开关" id="ops-runtime-config" />
        <ConfigGrid config={currentDiagnostics.config} />
      </section>
    </main>
  );
}

function SectionHeader({ detail, id, title }: { detail: string; id?: string; title: string }) {
  return (
    <header className="ops-section-header">
      <h2 id={id}>{title}</h2>
      <span>{detail}</span>
    </header>
  );
}

function CollectorSnapshot({ diagnostics }: { diagnostics: OpsDiagnostics }) {
  const details = objectValue(diagnostics.collector.details);
  const connection = objectValue(diagnostics.collector.connection);
  return (
    <div className="ops-live-grid">
      <MetricCell
        label="连接"
        value={runtimeStateLabel(stringValue(connection.state, "unknown"))}
      />
      <MetricCell label="原始帧" value={numberString(details.frames_received)} />
      <MetricCell label="Twitter 事件" value={numberString(details.twitter_events)} />
      <MetricCell label="匹配" value={numberString(details.matched_twitter_events)} />
      <MetricCell label="已发布" value={numberString(details.events_published)} />
      <MetricCell
        label="最近匹配"
        value={relativeLabel(numberValue(details.last_matched_event_at_ms))}
      />
    </div>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <span className="ops-metric-cell">
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}

function ChainCard({ lane }: { lane: ChainLane }) {
  return (
    <article className={clsx("ops-chain-card", `is-${lane.status}`)}>
      <div className="ops-chain-icon">{chainIcon(lane.icon)}</div>
      <div className="ops-chain-copy">
        <div>
          <h3>{lane.title}</h3>
          <StatusChip status={lane.status} />
        </div>
        <p>{lane.intent}</p>
        <dl>
          <div>
            <dt>当前</dt>
            <dd>{lane.primary}</dd>
          </div>
          <div>
            <dt>检查</dt>
            <dd>{lane.secondary}</dd>
          </div>
        </dl>
      </div>
    </article>
  );
}

function ProviderRow({ provider }: { provider: OpsProvider }) {
  return (
    <div className="ops-fleet-row">
      <span>
        <b>{provider.provider}</b>
        <small>{provider.domain}</small>
      </span>
      <StatusChip status={provider.status} />
      <em>{runtimeStateLabel(provider.reason)}</em>
    </div>
  );
}

function WorkerRow({ worker }: { worker: OpsWorker }) {
  const duration = numberValue(worker.iteration_duration_p99_ms);
  return (
    <div className="ops-fleet-row">
      <span>
        <b>{worker.name}</b>
        <small>{worker.group}</small>
      </span>
      <StatusChip status={worker.status} />
      <em>
        {runtimeStateLabel(worker.reason)}
        {duration === null ? "" : ` / p99 ${Math.round(duration)}ms`}
      </em>
    </div>
  );
}

function QueueButton({
  active,
  queue,
  onSelectQueue,
}: {
  active: boolean;
  queue: OpsQueueSummary;
  onSelectQueue: (queueName: string) => void;
}) {
  return (
    <button
      aria-label={`打开队列 ${queue.queue_name}`}
      className={clsx("ops-queue-button", active && "active")}
      type="button"
      onClick={() => onSelectQueue(queue.queue_name)}
    >
      <span className="ops-queue-title">
        <b>{queue.queue_name}</b>
        <small>{queue.worker_name}</small>
      </span>
      <StatusChip status={queue.status} />
      <span className="ops-queue-counts">
        <em>死信 {numberString(queue.dead_count)}</em>
        <em>待执行 {numberString(queue.due_count)}</em>
        <em>运行中 {numberString(queue.running_count)}</em>
      </span>
    </button>
  );
}

function QueueDetail({
  loading,
  queue,
  selectedQueueName,
}: {
  loading: boolean;
  queue: OpsQueueData | null | undefined;
  selectedQueueName: string | null;
}) {
  if (!selectedQueueName) {
    return (
      <div className="ops-queue-detail empty">
        <b>选择一个队列</b>
        <span>优先查看标记为阻塞或降级的队列。</span>
      </div>
    );
  }
  if (loading) {
    return <PageState.Loading label="加载队列" layout="inline" rows={3} />;
  }
  if (!queue) {
    return (
      <div className="ops-queue-detail empty">
        <b>{selectedQueueName}</b>
        <span>还没有加载到队列明细。</span>
      </div>
    );
  }
  let currentQueue: OpsQueueData;
  try {
    currentQueue = requireOpsQueueData(queue);
  } catch (contractError) {
    return <PageState.Error error={contractError} />;
  }
  return (
    <div className="ops-queue-detail">
      <header>
        <div>
          <b>{currentQueue.queue_name}</b>
          <span>{queueStatusLine(currentQueue.counts_by_status)}</span>
        </div>
        <StatusChip status={currentQueue.summary.status} />
      </header>
      <div className="ops-queue-rows">
        {currentQueue.items.slice(0, 12).map((item) => (
          <QueueItemRow item={item} key={`${String(item.id)}:${item.updated_at_ms ?? ""}`} />
        ))}
        {currentQueue.items.length === 0 ? (
          <span className="ops-empty-line">暂无活跃任务</span>
        ) : null}
      </div>
    </div>
  );
}

function QueueItemRow({ item }: { item: OpsQueueItem }) {
  return (
    <div className="ops-queue-row">
      <div>
        <b>{item.id === null || item.id === undefined ? "未知" : String(item.id)}</b>
        <div className="ops-source-line">
          {sourceEntries(item.source).map(([key, value]) => (
            <small key={key}>{`${key}: ${String(value)}`}</small>
          ))}
        </div>
      </div>
      <StatusChip status={statusTone(item.status)} />
      <span>{attemptLabel(item)}</span>
      <span>{item.updated_at_ms ? `${relativeTimeLabel(item.updated_at_ms)}前` : "未更新"}</span>
      <em>{item.last_error_type ?? "未记录错误"}</em>
    </div>
  );
}

function ConfigGrid({ config }: { config: Record<string, unknown> }) {
  const keys = [
    "app_home",
    "config_path",
    "workers_config_path",
    "handles_count",
    "gmgn_configured",
    "okx_dex_configured",
    "llm_configured",
    "news_enabled",
    "notifications_enabled",
  ];
  return (
    <div className="ops-config-grid">
      {keys.map((key) => (
        <span key={key}>
          <small>{key}</small>
          <b>{String(config[key] ?? "n/a")}</b>
        </span>
      ))}
    </div>
  );
}

function StatusChip({ status }: { status: string | null | undefined }) {
  const tone = statusTone(status);
  return <span className={clsx("ops-status-chip", `is-${tone}`)}>{statusLabel(tone)}</span>;
}

function StatusIcon({ status }: { status: OpsSectionStatus }) {
  if (status === "ok") {
    return <CheckCircle2 aria-hidden />;
  }
  if (status === "blocked" || status === "degraded") {
    return <AlertTriangle aria-hidden />;
  }
  if (status === "disabled" || status === "idle") {
    return <CircleDashed aria-hidden />;
  }
  return <ServerCog aria-hidden />;
}

function chainIcon(icon: ChainLane["icon"]) {
  if (icon === "activity") return <Activity aria-hidden />;
  if (icon === "database") return <Database aria-hidden />;
  if (icon === "workflow") return <Workflow aria-hidden />;
  if (icon === "list") return <ListChecks aria-hidden />;
  return <RadioTower aria-hidden />;
}

function runtimeChain(diagnostics: OpsDiagnostics): ChainLane[] {
  const collectorDetails = objectValue(diagnostics.collector.details);
  const agentExecutionStatus = diagnostics.agent_execution.status;
  const providerState = worstStatus(diagnostics.providers);
  const workerState = worstStatus(diagnostics.workers);

  return [
    {
      title: "Ingest",
      status: worstStatus([diagnostics.database, diagnostics.collector]),
      intent: "GMGN public stream 落库为 event facts。",
      primary: `${numberString(collectorDetails.events_published)} 条事件已发布`,
      secondary: `${numberString(collectorDetails.matched_twitter_events)} 条 Twitter 事件匹配`,
      icon: "activity",
    },
    {
      title: "Facts & Identity",
      status: worstStatus([diagnostics.domains.asset_market, diagnostics.domains.token_radar]),
      intent: "Asset identity、market ticks 和 Token Radar rows 在 Postgres 中物化。",
      primary: `Provider 输入输出${statusLabel(providerState)}`,
      secondary: `Worker 状态${statusLabel(workerState)}`,
      icon: "database",
    },
    {
      title: "News & Agent",
      status: worstStatus([diagnostics.domains.news, { status: agentExecutionStatus }]),
      intent: "News read models 与 Agent 执行状态保持各自可审计。",
      primary: `${numberString(diagnostics.domains.news.source_count)} 个新闻来源`,
      secondary: `新闻${statusLabel(statusTone(diagnostics.domains.news.status))} / Agent ${statusLabel(agentExecutionStatus)}`,
      icon: "workflow",
    },
    {
      title: "Delivery",
      status: worstStatus([diagnostics.domains.notifications, diagnostics.domains.watchlist]),
      intent: "Watchlist source monitor 和 notifications 服务操作员。",
      primary: `Watchlist${statusLabel(statusTone(diagnostics.domains.watchlist.status))}`,
      secondary: `通知${statusLabel(statusTone(diagnostics.domains.notifications.status))}`,
      icon: "list",
    },
  ];
}

function incidentRows(diagnostics: OpsDiagnostics): Array<{
  id: string;
  title: string;
  detail: string;
  status: OpsSectionStatus;
}> {
  const incidents: Array<{ id: string; title: string; detail: string; status: OpsSectionStatus }> =
    [];

  for (const queue of sortByAttention(diagnostics.queues)) {
    const dead = queue.dead_count;
    const failed = queue.failed_count;
    const due = queue.due_count;
    if (dead > 0) {
      incidents.push({
        id: `queue:${queue.queue_name}:dead`,
        title: `${queue.queue_name} 有 ${dead} 个死信任务`,
        detail: `${queue.worker_name} 负责该控制面队列；待执行 ${due} 个，运行中 ${numberString(queue.running_count)} 个。`,
        status: "blocked",
      });
      continue;
    }
    if (failed > 0) {
      incidents.push({
        id: `queue:${queue.queue_name}:failed`,
        title: `${queue.queue_name} 有 ${failed} 个可重试失败`,
        detail: `${queue.worker_name} 会通过有界 catch-up 自动恢复这些任务。`,
        status: "degraded",
      });
    }
  }

  for (const [name, payload] of Object.entries(diagnostics.domains)) {
    const status = statusTone(payload.status);
    if (status === "blocked" || status === "degraded" || status === "unknown") {
      incidents.push({
        id: `domain:${name}`,
        title: `${domainLabel(name)}${statusLabel(status)}`,
        detail: domainIncidentDetail(name, payload),
        status,
      });
    }
  }

  const agentStatus = statusTone(diagnostics.agent_execution.status);
  if (agentStatus === "blocked" || agentStatus === "degraded" || agentStatus === "unknown") {
    incidents.push({
      id: "agent_execution",
      title: `Agent 执行${statusLabel(agentStatus)}`,
      detail: agentIncidentDetail(diagnostics.agent_execution),
      status: agentStatus,
    });
  }

  return incidents
    .sort((left, right) => statusRank(right.status) - statusRank(left.status))
    .slice(0, 8);
}

function incidentSummary(diagnostics: OpsDiagnostics, visibleCount: number): string {
  const counts = diagnostics.overall.section_status_counts;
  const blocked = numberValue(counts.blocked);
  const degraded = numberValue(counts.degraded);
  if (blocked !== null && blocked > 0) {
    return degraded !== null ? `${blocked} 个阻塞 / ${degraded} 个降级` : `${blocked} 个阻塞`;
  }
  if (degraded !== null && degraded > 0) return `${degraded} 个降级`;
  return `${visibleCount} 个活跃问题`;
}

function domainIncidentDetail(name: string, payload: OpsJson): string {
  if (name === "news") {
    return `${numberString(payload.source_count)} 个来源，检查失败来源状态。`;
  }
  return stringValue(payload.reason ?? payload.error_type ?? payload.status, "需要检查");
}

function agentIncidentDetail(agentExecution: OpsAgentExecution): string {
  const policy = objectValue(agentExecution.policy);
  const lane = typeof policy.lane === "string" ? policy.lane : null;
  const detail = stringValue(
    agentExecution.error ?? agentExecution.status_reason,
    `Agent 执行${statusLabel(statusTone(agentExecution.status))}`,
  );
  return lane ? `${lane}: ${detail}` : detail;
}

function worstStatus(items: Array<{ status?: string | null } | undefined>): OpsSectionStatus {
  const order: OpsSectionStatus[] = ["blocked", "degraded", "unknown", "idle", "disabled", "ok"];
  const statuses = new Set(items.map((item) => statusTone(item?.status)));
  return order.find((status) => statuses.has(status)) ?? "unknown";
}

function sortByAttention<
  T extends { status?: string | null; name?: string; queue_name?: string; provider?: string },
>(items: T[]): T[] {
  return [...items].sort((left, right) => {
    const rankDelta = statusRank(right.status) - statusRank(left.status);
    if (rankDelta !== 0) return rankDelta;
    return String(left.name ?? left.queue_name ?? left.provider ?? "").localeCompare(
      String(right.name ?? right.queue_name ?? right.provider ?? ""),
    );
  });
}

function queueStatusLine(counts: Record<string, number>): string {
  const entries = Object.entries(counts).filter(([, value]) => value > 0);
  if (!entries.length) return "空队列";
  return entries.map(([key, value]) => `${queueStateLabel(key)}:${value}`).join(" / ");
}

function sourceEntries(source: OpsJson): Array<[string, unknown]> {
  const entries = Object.entries(source).filter(
    ([, value]) => value !== null && value !== undefined,
  );
  return entries.length ? entries.slice(0, 3) : [["source", "n/a"]];
}

function attemptLabel(item: OpsQueueItem): string {
  if (item.attempt_count === null || item.max_attempts === null) {
    return "尝试 未知";
  }
  return `尝试 ${item.attempt_count}/${item.max_attempts}`;
}

function relativeLabel(value: number | null): string {
  if (value === null) return "-";
  return `${relativeTimeLabel(value)}前`;
}

function numberString(value: unknown): string {
  const parsed = numberValue(value);
  return parsed === null ? "未知" : String(Math.round(parsed));
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function objectValue(value: unknown): OpsJson {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as OpsJson) : {};
}

function humanize(value: string): string {
  return value
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function domainLabel(value: string): string {
  switch (value) {
    case "asset_market":
      return "Asset Market";
    case "narrative":
      return "Narrative";
    case "news":
      return "News";
    case "notifications":
      return "Notifications";
    case "token_radar":
      return "Token Radar";
    case "watchlist":
      return "Watchlist";
    default:
      return humanize(value);
  }
}

function statusLabel(status: string | null | undefined): string {
  switch (statusTone(status)) {
    case "blocked":
      return "阻塞";
    case "degraded":
      return "降级";
    case "disabled":
      return "停用";
    case "idle":
      return "空闲";
    case "ok":
      return "正常";
    case "unknown":
      return "未知";
  }
}

function queueStateLabel(value: string): string {
  switch (value) {
    case "dead":
      return "死信";
    case "done":
      return "完成";
    case "failed":
      return "失败";
    case "pending":
      return "待处理";
    case "running":
      return "运行中";
    default:
      return value;
  }
}

function runtimeStateLabel(value: string | null | undefined): string {
  switch (value) {
    case "configured":
      return "已配置";
    case "connected":
      return "已连接";
    case "disabled":
      return "停用";
    case "idle":
      return "空闲";
    case "ready":
      return "就绪";
    case "running":
      return "运行中";
    case "streaming":
      return "流式接入中";
    case "unknown":
      return "未知";
    default:
      return value ?? "未知";
  }
}

function relativeTimeLabel(value: number): string {
  const raw = formatRelativeTime(value);
  const match = raw.match(/^(\d+)([smhd])$/);
  if (!match) return raw;
  const [, amount, unit] = match;
  switch (unit) {
    case "s":
      return `${amount} 秒`;
    case "m":
      return `${amount} 分钟`;
    case "h":
      return `${amount} 小时`;
    case "d":
      return `${amount} 天`;
    default:
      return raw;
  }
}
