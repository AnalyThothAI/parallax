export type OpsSectionStatus = "ok" | "idle" | "disabled" | "degraded" | "blocked" | "unknown";

export type OpsJson = Record<string, unknown>;

export type OpsProvider = {
  provider: string;
  domain: string;
  configured: boolean;
  capabilities?: string[];
  state?: string | null;
  last_state_change_at_ms?: number | null;
  last_error_type?: string | null;
  status: OpsSectionStatus;
  reason?: string | null;
};

export type OpsWorker = {
  name: string;
  group: string;
  enabled: boolean;
  running: boolean;
  last_started_at_ms?: number | null;
  last_finished_at_ms?: number | null;
  last_result?: OpsJson | null;
  last_error_type?: string | null;
  iteration_duration_p99_ms?: number | null;
  pool_wait_ms_p99?: number | null;
  queue_depth?: number | null;
  status: OpsSectionStatus;
  reason?: string | null;
};

export type OpsQueueSummary = {
  queue_name: string;
  table: string;
  worker_name: string;
  counts_by_status: Record<string, number>;
  due_count?: number | null;
  running_count?: number | null;
  dead_count?: number | null;
  failed_count?: number | null;
  oldest_due_age_ms?: number | null;
  oldest_running_age_ms?: number | null;
  status: OpsSectionStatus;
  reason?: string | null;
};

export type OpsDiagnostics = {
  schema_version: string;
  generated_at_ms?: number | null;
  overall: {
    status?: OpsSectionStatus;
    severity?: string | null;
    reasons?: string[];
    section_status_counts?: Record<string, number>;
  };
  config: OpsJson;
  database: OpsJson & { status?: OpsSectionStatus };
  collector: OpsJson & { status?: OpsSectionStatus };
  providers: OpsProvider[];
  workers: OpsWorker[];
  queues: OpsQueueSummary[];
  domains: Record<string, OpsJson & { status?: OpsSectionStatus; reason?: string | null }>;
  suggested_checks?: OpsJson[];
};

export type OpsQueueItem = {
  id?: string | null;
  status?: string | null;
  attempt_count?: number | null;
  max_attempts?: number | null;
  created_at_ms?: number | null;
  updated_at_ms?: number | null;
  next_run_at_ms?: number | null;
  last_error_type?: string | null;
  last_error_preview?: string | null;
  source?: OpsJson;
};

export type OpsQueueData = {
  schema_version: string;
  queue_name: string;
  status_filter?: string | null;
  counts_by_status: Record<string, number>;
  summary: OpsQueueSummary;
  items: OpsQueueItem[];
};

export function statusTone(status: string | null | undefined): OpsSectionStatus {
  if (
    status === "ok" ||
    status === "idle" ||
    status === "disabled" ||
    status === "degraded" ||
    status === "blocked" ||
    status === "unknown"
  ) {
    return status;
  }
  return "unknown";
}

export function statusRank(status: string | null | undefined): number {
  switch (statusTone(status)) {
    case "blocked":
      return 5;
    case "degraded":
      return 4;
    case "unknown":
      return 3;
    case "idle":
      return 2;
    case "disabled":
      return 1;
    case "ok":
      return 0;
  }
}

export function domainRows(diagnostics: OpsDiagnostics): Array<{
  name: string;
  status: OpsSectionStatus;
  reason: string;
  backlog: string;
}> {
  return Object.entries(diagnostics.domains)
    .map(([name, payload]) => ({
      name,
      status: statusTone(payload.status),
      reason: stringValue(payload.reason ?? payload.error_type ?? payload.status),
      backlog: backlogValue(payload),
    }))
    .sort((left, right) => statusRank(right.status) - statusRank(left.status));
}

export function formatCount(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return "0";
}

function backlogValue(payload: OpsJson): string {
  const candidates = [
    payload.due_jobs,
    payload.total_pending,
    payload.pending_digest_count,
    payload.failed_jobs_4h,
    payload.dead_jobs,
  ];
  const first = candidates.find((item) => typeof item === "number" && Number.isFinite(item));
  return formatCount(first);
}

function stringValue(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "ready";
}
