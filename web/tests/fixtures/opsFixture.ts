import type { OpsAgentExecution, OpsDiagnostics, OpsQueueData } from "@features/ops";

export function activeOpsAgentExecutionFixture(): OpsAgentExecution {
  return {
    status: "ok",
    policy: {
      lane: "news.story_brief",
      model: "deepseek-v4-flash",
      provider_family: "deepseek",
      output_strategy: "json_object",
      schema_enforcement: "client_validate",
      max_concurrency: 1,
      rpm_limit: 60,
      timeout_seconds: 180,
    },
    counters: {
      in_flight: 0,
      provider_running: 0,
      circuit_state: "closed",
      circuit_open_until_ms: null,
      capacity_denied_total: 0,
      circuit_open_total: 0,
      timeout_total: 0,
      last_denied_at_ms: null,
      last_timeout_at_ms: null,
      oldest_in_flight_age_ms: null,
    },
  };
}

export function opsDiagnosticsFixture(): OpsDiagnostics {
  return {
    schema_version: "ops.diagnostics.v1",
    generated_at_ms: 1_700_000_000_000,
    overall: {
      status: "degraded",
      severity: "warning",
      reasons: ["retryable_failures_present"],
      section_status_counts: { ok: 4, degraded: 1 },
    },
    config: {
      app_home: "/Users/qinghuan/.parallax",
      config_path: "/Users/qinghuan/.parallax/config.yaml",
      workers_config_path: "/Users/qinghuan/.parallax/workers.yaml",
      handles_count: 3,
      upstream_channels: ["new_pairs"],
      gmgn_configured: true,
      okx_dex_configured: true,
      llm_configured: false,
      news_enabled: true,
      notifications_enabled: true,
    },
    database: { status: "ok", ok: true, probe: "postgres_liveness", schema: {} },
    collector: {
      status: "ok",
      connection: { state: "connected" },
      details: { frames_received: 12, matched_twitter_events: 4, events_published: 3 },
    },
    providers: [
      {
        provider: "gmgn",
        domain: "asset_market",
        configured: true,
        capabilities: ["quote_dex_exact"],
        state: "configured",
        last_state_change_at_ms: null,
        last_error_type: null,
        status: "ok",
        reason: "ready",
      },
    ],
    workers: [
      {
        name: "token_radar_projection",
        group: "asset_market",
        enabled: true,
        running: true,
        effective_status: "running",
        unavailable_reason: null,
        last_started_at_ms: 1_700_000_000_000,
        last_finished_at_ms: null,
        last_result: null,
        last_error_type: null,
        iteration_duration_p99_ms: 18,
        status: "running",
        reason: "running",
      },
    ],
    queues: [
      {
        queue_name: "notification_deliveries",
        table: "notification_deliveries",
        worker_name: "notification_delivery",
        counts_by_status: { dead: 1, pending: 2, running: 1 },
        due_count: 2,
        running_count: 0,
        dead_count: 1,
        failed_count: 0,
        oldest_due_age_ms: 90_000,
        oldest_running_age_ms: null,
        status: "blocked",
        reason: "dead_jobs_present",
      },
    ],
    agent_execution: {
      status: "disabled",
      policy: null,
      counters: null,
    },
    domains: {
      token_radar: { status: "ok", publication: { status: "ready" } },
      asset_market: { status: "ok", configured_provider_count: 1, provider_count: 1 },
      news: { status: "ok", sources: [{ source: "fixture" }], source_count: 1 },
      watchlist: { status: "ok", configured_handle_count: 2 },
      notifications: {
        status: "blocked",
        summary: {
          subscriber_key: "local",
          unread_count: 1,
          high_unread_count: 1,
          critical_unread_count: 0,
          highest_unread_severity: "high",
          account_unread_counts: { traderpow: 1 },
        },
      },
    },
    suggested_checks: [
      {
        id: "inspect_worker_status",
        label: "inspect worker queues",
        reason: "blocked queue detected",
        cli_equivalent: "GET /api/ops/diagnostics",
        safe_to_run: true,
        requires_confirmation: false,
      },
      {
        id: "inspect_news_sources",
        label: "inspect news sources",
        reason: "news source health is not ready",
        cli_equivalent: "GET /api/news/sources/status",
        safe_to_run: true,
        requires_confirmation: false,
      },
    ],
  };
}

export function opsQueueFixture(): OpsQueueData {
  const diagnostics = opsDiagnosticsFixture();
  return {
    schema_version: "ops.queue.v1",
    queue_name: "notification_deliveries",
    status_filter: null,
    counts_by_status: { dead: 1, pending: 2, running: 1 },
    summary: diagnostics.queues[0],
    items: [
      {
        id: "delivery-1",
        status: "dead",
        attempt_count: 2,
        max_attempts: 3,
        created_at_ms: 1_699_999_900_000,
        updated_at_ms: 1_700_000_000_000,
        next_run_at_ms: 1_700_000_030_000,
        last_attempt_at_ms: 1_700_000_000_000,
        delivered_at_ms: null,
        last_error_type: "RuntimeError",
        last_error_preview: "delivery failed",
        source: {
          notification_id: "notification-1",
          channel: "in_app",
        },
      },
    ],
  };
}
