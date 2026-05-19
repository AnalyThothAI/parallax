import { formatRelativeTime } from "@lib/format";
import { RemoteState } from "@shared/ui/RemoteState";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, CircleDashed, ServerCog } from "lucide-react";

import {
  domainRows,
  statusTone,
  type OpsDiagnostics,
  type OpsProvider,
  type OpsQueueData,
  type OpsQueueSummary,
  type OpsSectionStatus,
  type OpsWorker,
} from "../model/opsDiagnostics";
import "./ops.css";

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
    return <RemoteState.Loading label="loading ops diagnostics" layout="route" rows={6} />;
  }
  if (error) {
    return <RemoteState.Error error={error} onRetry={onRefresh} />;
  }
  if (!diagnostics) {
    return <RemoteState.Empty title="No diagnostics" hint="Runtime diagnostics are unavailable." />;
  }

  const rows = domainRows(diagnostics);

  return (
    <main className="ops-page">
      <header className="ops-hero">
        <div>
          <p>control plane</p>
          <h1>Ops Diagnostics</h1>
        </div>
        <StatusChip status={diagnostics.overall.status} />
      </header>

      <section className="ops-health-strip" aria-label="health summary">
        <HealthTile label="DB" payload={diagnostics.database} />
        <HealthTile label="Collector" payload={diagnostics.collector} />
        <HealthTile label="Providers" status={worstStatus(diagnostics.providers)} />
        <HealthTile label="Workers" status={worstStatus(diagnostics.workers)} />
        <HealthTile label="Queues" status={worstStatus(diagnostics.queues)} />
        <HealthTile label="Domains" status={worstStatus(Object.values(diagnostics.domains))} />
      </section>

      <section className="ops-band">
        <SectionHeader title="Pipeline" detail="domain lanes" />
        <div className="ops-table ops-pipeline-table">
          {rows.map((row) => (
            <div className="ops-table-row" key={row.name}>
              <b>{row.name}</b>
              <StatusChip status={row.status} />
              <span>{row.reason}</span>
              <em>{row.backlog}</em>
            </div>
          ))}
        </div>
      </section>

      <section className="ops-grid">
        <div className="ops-band">
          <SectionHeader title="Providers" detail={`${diagnostics.providers.length} wired`} />
          <div className="ops-matrix">
            {diagnostics.providers.map((provider) => (
              <ProviderRow key={`${provider.domain}:${provider.provider}`} provider={provider} />
            ))}
          </div>
        </div>
        <div className="ops-band">
          <SectionHeader title="Workers" detail={`${diagnostics.workers.length} canonical`} />
          <div className="ops-matrix">
            {diagnostics.workers.map((worker) => (
              <WorkerRow key={worker.name} worker={worker} />
            ))}
          </div>
        </div>
      </section>

      <section className="ops-band">
        <SectionHeader title="Queues" detail={`${diagnostics.queues.length} allowlisted`} />
        <div className="ops-queue-layout">
          <div className="ops-queue-list">
            {diagnostics.queues.map((item) => (
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

      <section className="ops-band ops-config">
        <SectionHeader title="Config Source" detail="redacted runtime paths" />
        <ConfigGrid config={diagnostics.config} />
      </section>
    </main>
  );
}

function SectionHeader({ detail, title }: { detail: string; title: string }) {
  return (
    <header className="ops-section-header">
      <h2>{title}</h2>
      <span>{detail}</span>
    </header>
  );
}

function HealthTile({
  label,
  payload,
  status,
}: {
  label: string;
  payload?: { status?: string; reason?: string; probe?: string };
  status?: string;
}) {
  const resolved = statusTone(status ?? payload?.status);
  return (
    <div className={clsx("ops-health-tile", `is-${resolved}`)}>
      <StatusIcon status={resolved} />
      <span>{label}</span>
      <b>{resolved}</b>
      <small>{payload?.reason ?? payload?.probe ?? "ready"}</small>
    </div>
  );
}

function ProviderRow({ provider }: { provider: OpsProvider }) {
  return (
    <div className="ops-matrix-row">
      <div>
        <b>{provider.provider}</b>
        <span>{provider.domain}</span>
      </div>
      <StatusChip status={provider.status} />
      <small>{provider.state ?? (provider.configured ? "configured" : "disabled")}</small>
      <em>{provider.reason ?? provider.last_error_type ?? "ready"}</em>
    </div>
  );
}

function WorkerRow({ worker }: { worker: OpsWorker }) {
  return (
    <div className="ops-matrix-row">
      <div>
        <b>{worker.name}</b>
        <span>{worker.group}</span>
      </div>
      <StatusChip status={worker.status} />
      <small>{worker.running ? "running" : worker.enabled ? "idle" : "disabled"}</small>
      <em>{worker.queue_depth === null || worker.queue_depth === undefined ? "queue n/a" : `q ${worker.queue_depth}`}</em>
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
      aria-label={`open queue ${queue.queue_name}`}
      className={clsx("ops-queue-button", active && "active")}
      type="button"
      onClick={() => onSelectQueue(queue.queue_name)}
    >
      <span>
        <b>{queue.queue_name}</b>
        <small>{queue.worker_name}</small>
      </span>
      <StatusChip status={queue.status} />
      <em>{queue.reason ?? "ready"}</em>
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
    return <div className="ops-queue-detail empty">select a queue</div>;
  }
  if (loading) {
    return <RemoteState.Loading label="loading queue" layout="inline" rows={3} />;
  }
  if (!queue) {
    return <div className="ops-queue-detail empty">no queue rows</div>;
  }
  return (
    <div className="ops-queue-detail">
      <header>
        <b>{queue.queue_name}</b>
        <span>{Object.entries(queue.counts_by_status).map(([key, value]) => `${key}:${value}`).join(" · ") || "empty"}</span>
      </header>
      <div className="ops-queue-rows">
        {queue.items.slice(0, 8).map((item) => (
          <div className="ops-queue-row" key={`${item.id ?? "job"}:${item.updated_at_ms ?? ""}`}>
            <b>{String(item.id ?? "unknown")}</b>
            <StatusChip status={statusTone(item.status)} />
            <span>{item.updated_at_ms ? `${formatRelativeTime(item.updated_at_ms)} ago` : "no update"}</span>
            <em>{item.last_error_type ?? "ready"}</em>
          </div>
        ))}
        {queue.items.length === 0 ? <span className="ops-empty-line">no active rows</span> : null}
      </div>
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
  return <span className={clsx("ops-status-chip", `is-${tone}`)}>{tone}</span>;
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

function worstStatus(items: Array<{ status?: string | null }>): OpsSectionStatus {
  const order: OpsSectionStatus[] = ["blocked", "degraded", "unknown", "idle", "disabled", "ok"];
  const statuses = new Set(items.map((item) => statusTone(item.status)));
  return order.find((status) => statuses.has(status)) ?? "unknown";
}
