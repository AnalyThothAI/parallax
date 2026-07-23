export type OpsSectionStatus = "ok" | "idle" | "disabled" | "degraded" | "blocked" | "unknown";

export type OpsRuntimeStatus =
  | OpsSectionStatus
  | "failed"
  | "unavailable"
  | "intentionally_not_started"
  | "running"
  | "stopped";

export type OpsJson = Record<string, unknown>;

export type OpsProvider = {
  provider: string;
  domain: string;
  configured: boolean;
  capabilities: string[];
  state: string;
  last_state_change_at_ms: number | null;
  last_error_type: string | null;
  status: OpsRuntimeStatus;
  reason: string;
};

export type OpsWorker = {
  name: string;
  group: string;
  enabled: boolean;
  running: boolean;
  effective_status: OpsRuntimeStatus;
  unavailable_reason: string | null;
  last_started_at_ms: number | null;
  last_finished_at_ms: number | null;
  last_result: OpsJson | null;
  last_error_type: string | null;
  iteration_duration_p99_ms: number | null;
  status: OpsRuntimeStatus;
  reason: string;
};

export type OpsQueueSummary = {
  queue_name: string;
  table: string;
  worker_name: string;
  counts_by_status: Record<string, number>;
  due_count: number;
  running_count: number;
  dead_count: number;
  failed_count: number;
  oldest_due_age_ms: number | null;
  oldest_running_age_ms: number | null;
  status: OpsRuntimeStatus;
  reason: string;
};

export type OpsDiagnostics = {
  schema_version: "ops.diagnostics.v1";
  generated_at_ms: number;
  overall: {
    status: OpsSectionStatus;
    severity: string;
    reasons: string[];
    section_status_counts: Record<string, number>;
  };
  config: OpsJson;
  database: OpsJson & { status: OpsRuntimeStatus };
  collector: OpsJson & { status: OpsRuntimeStatus };
  providers: OpsProvider[];
  workers: OpsWorker[];
  queues: OpsQueueSummary[];
  domains: Record<string, OpsJson & { status: OpsRuntimeStatus; reason?: string | null }>;
  suggested_checks: Array<
    OpsJson & {
      id: string;
      label: string;
      reason: string;
      cli_equivalent: string;
      safe_to_run: boolean;
      requires_confirmation: boolean;
    }
  >;
};

export type OpsQueueItem = {
  id: unknown;
  status: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  created_at_ms: number | null;
  updated_at_ms: number | null;
  next_run_at_ms: number | null;
  last_attempt_at_ms: number | null;
  delivered_at_ms: number | null;
  last_error_type: string | null;
  last_error_preview: string | null;
  source: OpsJson;
};

export type OpsQueueData = {
  schema_version: "ops.queue.v1";
  queue_name: string;
  status_filter: string | null;
  counts_by_status: Record<string, number>;
  summary: OpsQueueSummary;
  items: OpsQueueItem[];
};

const DIAGNOSTIC_KEYS = [
  "schema_version",
  "generated_at_ms",
  "overall",
  "config",
  "database",
  "collector",
  "providers",
  "workers",
  "queues",
  "domains",
  "suggested_checks",
] as const;
const DOMAIN_KEYS = ["token_radar", "asset_market", "news", "watchlist", "notifications"] as const;
const DATABASE_SECTION_KEYS = [
  "status",
  "ok",
  "probe",
  "schema",
  "detail",
  "error",
  "original_error",
  "original_detail",
] as const;
const DATABASE_SECTION_REQUIRED_KEYS = ["status", "ok", "probe", "schema"] as const;
const COLLECTOR_SECTION_KEYS = ["status", "connection", "details"] as const;
const NOTIFICATION_SUMMARY_KEYS = [
  "subscriber_key",
  "unread_count",
  "high_unread_count",
  "critical_unread_count",
  "highest_unread_severity",
  "account_unread_counts",
] as const;
const RUNTIME_STATUSES = new Set<OpsRuntimeStatus>([
  "ok",
  "idle",
  "disabled",
  "degraded",
  "blocked",
  "unknown",
  "failed",
  "unavailable",
  "intentionally_not_started",
  "running",
  "stopped",
]);

export function requireOpsDiagnostics(value: unknown): OpsDiagnostics {
  const diagnostics = requireRecord(value, "diagnostics");
  requireExactKeys(diagnostics, DIAGNOSTIC_KEYS, "diagnostics");
  if (diagnostics.schema_version !== "ops.diagnostics.v1") {
    fail("diagnostics.schema_version");
  }
  requireFiniteNumber(diagnostics.generated_at_ms, "diagnostics.generated_at_ms");
  validateOverall(diagnostics.overall);
  validateConfig(diagnostics.config);
  const database = validateSection(
    diagnostics.database,
    "diagnostics.database",
    DATABASE_SECTION_KEYS,
    DATABASE_SECTION_REQUIRED_KEYS,
  );
  if (database) validateDatabaseSection(database);
  const collector = validateSection(
    diagnostics.collector,
    "diagnostics.collector",
    COLLECTOR_SECTION_KEYS,
    COLLECTOR_SECTION_KEYS,
  );
  if (collector) validateCollectorSection(collector);
  validateProviders(diagnostics.providers);
  validateWorkers(diagnostics.workers);
  validateQueueSummaries(diagnostics.queues, "diagnostics.queues");
  validateDomains(diagnostics.domains);
  validateSuggestedChecks(diagnostics.suggested_checks);
  return diagnostics as OpsDiagnostics;
}

export function requireOpsQueueData(value: unknown): OpsQueueData {
  const queue = requireRecord(value, "queue");
  requireExactKeys(
    queue,
    ["schema_version", "queue_name", "status_filter", "counts_by_status", "summary", "items"],
    "queue",
  );
  if (queue.schema_version !== "ops.queue.v1") {
    fail("queue.schema_version");
  }
  requireString(queue.queue_name, "queue.queue_name");
  requireNullableString(queue.status_filter, "queue.status_filter");
  validateCountRecord(queue.counts_by_status, "queue.counts_by_status");
  validateQueueSummary(queue.summary, "queue.summary");
  for (const [index, itemValue] of requireArray(queue.items, "queue.items").entries()) {
    const path = `queue.items.${index}`;
    const item = requireRecord(itemValue, path);
    requireExactKeys(
      item,
      [
        "id",
        "status",
        "attempt_count",
        "max_attempts",
        "created_at_ms",
        "updated_at_ms",
        "next_run_at_ms",
        "last_attempt_at_ms",
        "delivered_at_ms",
        "last_error_type",
        "last_error_preview",
        "source",
      ],
      path,
    );
    requireNullableString(item.status, `${path}.status`);
    for (const key of [
      "attempt_count",
      "max_attempts",
      "created_at_ms",
      "updated_at_ms",
      "next_run_at_ms",
      "last_attempt_at_ms",
      "delivered_at_ms",
    ]) {
      requireNullableFiniteNumber(item[key], `${path}.${key}`);
    }
    requireNullableString(item.last_error_type, `${path}.last_error_type`);
    requireNullableString(item.last_error_preview, `${path}.last_error_preview`);
    requireRecord(item.source, `${path}.source`);
  }
  return queue as OpsQueueData;
}

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
  if (status === "failed" || status === "unavailable") {
    return "blocked";
  }
  if (status === "running") {
    return "ok";
  }
  if (status === "stopped") {
    return "idle";
  }
  if (status === "intentionally_not_started") {
    return "disabled";
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
  return "未知";
}

function validateOverall(value: unknown): void {
  const overall = requireRecord(value, "diagnostics.overall");
  requireExactKeys(
    overall,
    ["status", "severity", "reasons", "section_status_counts"],
    "diagnostics.overall",
  );
  const status = requireRuntimeStatus(overall.status, "diagnostics.overall.status");
  if (statusTone(status) !== status) {
    fail("diagnostics.overall.status");
  }
  requireString(overall.severity, "diagnostics.overall.severity");
  requireStringArray(overall.reasons, "diagnostics.overall.reasons");
  validateCountRecord(overall.section_status_counts, "diagnostics.overall.section_status_counts");
}

function validateConfig(value: unknown): void {
  const config = requireRecord(value, "diagnostics.config");
  requireExactKeys(
    config,
    [
      "app_home",
      "config_path",
      "workers_config_path",
      "handles_count",
      "upstream_channels",
      "gmgn_configured",
      "okx_dex_configured",
      "news_enabled",
      "notifications_enabled",
    ],
    "diagnostics.config",
  );
  for (const key of ["app_home", "config_path", "workers_config_path"]) {
    requireNullableString(config[key], `diagnostics.config.${key}`);
  }
  requireFiniteNumber(config.handles_count, "diagnostics.config.handles_count");
  requireStringArray(config.upstream_channels, "diagnostics.config.upstream_channels");
  for (const key of [
    "gmgn_configured",
    "okx_dex_configured",
    "news_enabled",
    "notifications_enabled",
  ]) {
    requireBoolean(config[key], `diagnostics.config.${key}`);
  }
}

function validateSection(
  value: unknown,
  path: string,
  allowedKeys: readonly string[],
  requiredKeys: readonly string[],
): OpsJson | null {
  const section = requireRecord(value, path);
  const status = requireRuntimeStatus(section.status, `${path}.status`);
  if (status === "unknown" && Object.hasOwn(section, "section")) {
    requireExactKeys(section, ["status", "section", "error_type", "reason"], path);
    requireString(section.section, `${path}.section`);
    requireString(section.error_type, `${path}.error_type`);
    requireString(section.reason, `${path}.reason`);
    return null;
  }
  requireAllowedKeys(section, allowedKeys, requiredKeys, path);
  return section;
}

function validateDatabaseSection(database: OpsJson): void {
  const path = "diagnostics.database";
  requireBoolean(database.ok, `${path}.ok`);
  if (database.probe !== "postgres_liveness") fail(`${path}.probe`);
  requireRecord(database.schema, `${path}.schema`);
  for (const key of ["detail", "error", "original_error", "original_detail"]) {
    if (Object.hasOwn(database, key)) requireNullableString(database[key], `${path}.${key}`);
  }
}

function validateCollectorSection(collector: OpsJson): void {
  requireRecord(collector.connection, "diagnostics.collector.connection");
  requireRecord(collector.details, "diagnostics.collector.details");
}

function validateProviders(value: unknown): void {
  for (const [index, providerValue] of requireArray(value, "diagnostics.providers").entries()) {
    const path = `diagnostics.providers.${index}`;
    const provider = requireRecord(providerValue, path);
    requireExactKeys(
      provider,
      [
        "provider",
        "domain",
        "configured",
        "capabilities",
        "state",
        "last_state_change_at_ms",
        "last_error_type",
        "status",
        "reason",
      ],
      path,
    );
    requireString(provider.provider, `${path}.provider`);
    requireString(provider.domain, `${path}.domain`);
    requireBoolean(provider.configured, `${path}.configured`);
    requireStringArray(provider.capabilities, `${path}.capabilities`);
    requireString(provider.state, `${path}.state`);
    requireNullableFiniteNumber(
      provider.last_state_change_at_ms,
      `${path}.last_state_change_at_ms`,
    );
    requireNullableString(provider.last_error_type, `${path}.last_error_type`);
    requireRuntimeStatus(provider.status, `${path}.status`);
    requireString(provider.reason, `${path}.reason`);
  }
}

function validateWorkers(value: unknown): void {
  for (const [index, workerValue] of requireArray(value, "diagnostics.workers").entries()) {
    const path = `diagnostics.workers.${index}`;
    const worker = requireRecord(workerValue, path);
    requireExactKeys(
      worker,
      [
        "name",
        "group",
        "enabled",
        "running",
        "effective_status",
        "unavailable_reason",
        "last_started_at_ms",
        "last_finished_at_ms",
        "last_result",
        "last_error_type",
        "iteration_duration_p99_ms",
        "status",
        "reason",
      ],
      path,
    );
    requireString(worker.name, `${path}.name`);
    requireString(worker.group, `${path}.group`);
    requireBoolean(worker.enabled, `${path}.enabled`);
    requireBoolean(worker.running, `${path}.running`);
    const effectiveStatus = requireRuntimeStatus(
      worker.effective_status,
      `${path}.effective_status`,
    );
    if (requireRuntimeStatus(worker.status, `${path}.status`) !== effectiveStatus) {
      fail(`${path}.status`);
    }
    requireNullableString(worker.unavailable_reason, `${path}.unavailable_reason`);
    requireNullableFiniteNumber(worker.last_started_at_ms, `${path}.last_started_at_ms`);
    requireNullableFiniteNumber(worker.last_finished_at_ms, `${path}.last_finished_at_ms`);
    requireNullableRecord(worker.last_result, `${path}.last_result`);
    requireNullableString(worker.last_error_type, `${path}.last_error_type`);
    requireNullableFiniteNumber(
      worker.iteration_duration_p99_ms,
      `${path}.iteration_duration_p99_ms`,
    );
    requireString(worker.reason, `${path}.reason`);
  }
}

function validateQueueSummaries(value: unknown, path: string): void {
  for (const [index, summary] of requireArray(value, path).entries()) {
    validateQueueSummary(summary, `${path}.${index}`);
  }
}

function validateQueueSummary(value: unknown, path: string): void {
  const summary = requireRecord(value, path);
  requireExactKeys(
    summary,
    [
      "queue_name",
      "table",
      "worker_name",
      "counts_by_status",
      "due_count",
      "running_count",
      "dead_count",
      "failed_count",
      "oldest_due_age_ms",
      "oldest_running_age_ms",
      "status",
      "reason",
    ],
    path,
  );
  requireString(summary.queue_name, `${path}.queue_name`);
  requireString(summary.table, `${path}.table`);
  requireString(summary.worker_name, `${path}.worker_name`);
  validateCountRecord(summary.counts_by_status, `${path}.counts_by_status`);
  for (const key of ["due_count", "running_count", "dead_count", "failed_count"]) {
    requireFiniteNumber(summary[key], `${path}.${key}`);
  }
  requireNullableFiniteNumber(summary.oldest_due_age_ms, `${path}.oldest_due_age_ms`);
  requireNullableFiniteNumber(summary.oldest_running_age_ms, `${path}.oldest_running_age_ms`);
  requireRuntimeStatus(summary.status, `${path}.status`);
  requireString(summary.reason, `${path}.reason`);
}

function validateDomains(value: unknown): void {
  const domains = requireRecord(value, "diagnostics.domains");
  requireExactKeys(domains, DOMAIN_KEYS, "diagnostics.domains");
  for (const domainName of DOMAIN_KEYS) {
    const path = `diagnostics.domains.${domainName}`;
    const domain = requireRecord(domains[domainName], path);
    const status = requireRuntimeStatus(domain.status, `${path}.status`);
    if (status === "unknown" && Object.hasOwn(domain, "section")) {
      requireExactKeys(domain, ["status", "section", "error_type", "reason"], path);
      requireString(domain.section, `${path}.section`);
      requireString(domain.error_type, `${path}.error_type`);
      requireString(domain.reason, `${path}.reason`);
      continue;
    }
    if (domainName === "token_radar") {
      requireExactKeys(domain, ["status", "publication"], path);
      requireRecord(domain.publication, `${path}.publication`);
    }
    if (domainName === "asset_market") {
      requireExactKeys(domain, ["status", "configured_provider_count", "provider_count"], path);
      requireFiniteNumber(domain.configured_provider_count, `${path}.configured_provider_count`);
      requireFiniteNumber(domain.provider_count, `${path}.provider_count`);
    }
    if (domainName === "news") {
      requireExactKeys(domain, ["status", "sources", "source_count"], path);
      requireRecordArray(domain.sources, `${path}.sources`);
      requireFiniteNumber(domain.source_count, `${path}.source_count`);
    }
    if (domainName === "watchlist") {
      requireExactKeys(domain, ["status", "configured_handle_count"], path);
      requireFiniteNumber(domain.configured_handle_count, `${path}.configured_handle_count`);
    }
    if (domainName === "notifications") {
      requireExactKeys(domain, ["status", "summary"], path);
      validateNotificationSummary(domain.summary, `${path}.summary`);
    }
  }
}

function validateNotificationSummary(value: unknown, path: string): void {
  const summary = requireRecord(value, path);
  requireExactKeys(summary, NOTIFICATION_SUMMARY_KEYS, path);
  requireString(summary.subscriber_key, `${path}.subscriber_key`);
  for (const key of ["unread_count", "high_unread_count", "critical_unread_count"]) {
    requireFiniteNumber(summary[key], `${path}.${key}`);
  }
  requireNullableString(summary.highest_unread_severity, `${path}.highest_unread_severity`);
  validateCountRecord(summary.account_unread_counts, `${path}.account_unread_counts`);
}

function validateSuggestedChecks(value: unknown): void {
  for (const [index, checkValue] of requireArray(value, "diagnostics.suggested_checks").entries()) {
    const path = `diagnostics.suggested_checks.${index}`;
    const check = requireRecord(checkValue, path);
    requireExactKeys(
      check,
      ["id", "label", "reason", "cli_equivalent", "safe_to_run", "requires_confirmation"],
      path,
    );
    requireString(check.id, `${path}.id`);
    requireString(check.label, `${path}.label`);
    requireString(check.reason, `${path}.reason`);
    requireString(check.cli_equivalent, `${path}.cli_equivalent`);
    requireBoolean(check.safe_to_run, `${path}.safe_to_run`);
    requireBoolean(check.requires_confirmation, `${path}.requires_confirmation`);
  }
}

function backlogValue(payload: OpsJson): string {
  const candidates = [
    payload.due_jobs,
    payload.total_pending,
    payload.failed_jobs_4h,
    payload.dead_jobs,
  ];
  const first = candidates.find((item) => typeof item === "number" && Number.isFinite(item));
  return formatCount(first);
}

function stringValue(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "unknown";
}

function validateCountRecord(value: unknown, path: string): void {
  const counts = requireRecord(value, path);
  for (const [key, count] of Object.entries(counts)) {
    requireFiniteNumber(count, `${path}.${key}`);
  }
}

function requireRuntimeStatus(value: unknown, path: string): OpsRuntimeStatus {
  if (typeof value !== "string" || !RUNTIME_STATUSES.has(value as OpsRuntimeStatus)) {
    fail(path);
  }
  return value as OpsRuntimeStatus;
}

function requireRecordArray(value: unknown, path: string): OpsJson[] {
  return requireArray(value, path).map((item, index) => requireRecord(item, `${path}.${index}`));
}

function requireStringArray(value: unknown, path: string): string[] {
  return requireArray(value, path).map((item, index) => requireString(item, `${path}.${index}`));
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) fail(path);
  return value;
}

function requireRecord(value: unknown, path: string): OpsJson {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(path);
  return value as OpsJson;
}

function requireNullableRecord(value: unknown, path: string): OpsJson | null {
  return value === null ? null : requireRecord(value, path);
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string") fail(path);
  return value;
}

function requireNullableString(value: unknown, path: string): string | null {
  if (value !== null && typeof value !== "string") fail(path);
  return value;
}

function requireFiniteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(path);
  return value;
}

function requireNullableFiniteNumber(value: unknown, path: string): number | null {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) fail(path);
  return value;
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(path);
  return value;
}

function requireExactKeys(value: OpsJson, keys: readonly string[], path: string): void {
  requireAllowedKeys(value, keys, keys, path);
}

function requireAllowedKeys(
  value: OpsJson,
  allowedKeys: readonly string[],
  requiredKeys: readonly string[],
  path: string,
): void {
  const actual = Object.keys(value);
  if (
    actual.some((key) => !allowedKeys.includes(key)) ||
    requiredKeys.some((key) => !Object.hasOwn(value, key))
  ) {
    fail(path);
  }
}

function fail(path: string): never {
  throw new Error(`ops_current_contract:${path}`);
}
