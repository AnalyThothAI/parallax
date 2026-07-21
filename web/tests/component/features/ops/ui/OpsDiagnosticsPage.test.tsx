import { OpsDiagnosticsPage } from "@features/ops";
import type { OpsDiagnostics } from "@features/ops";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("OpsDiagnosticsPage", () => {
  it("renders the command-center summary, chain lanes, and queue selection", () => {
    const onSelectQueue = vi.fn();

    render(
      <OpsDiagnosticsPage
        diagnostics={fakeDiagnostics}
        loading={false}
        queue={null}
        selectedQueueName={null}
        onSelectQueue={onSelectQueue}
      />,
    );

    expect(screen.getByText("运维诊断")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "故障看板" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "运行链路" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Worker 状态" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "队列排查" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "运行配置" })).toBeInTheDocument();
    expect(screen.getByText("notification_deliveries 有 1 个死信任务")).toBeInTheDocument();
    expect(screen.getByText("建议检查 2 项")).toBeInTheDocument();
    expect(screen.getByText("Ingest")).toBeInTheDocument();
    expect(screen.getByText("Facts & Identity")).toBeInTheDocument();
    expect(screen.getByText("News & Agent")).toBeInTheDocument();
    expect(screen.getByText("notification_deliveries")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /打开队列 notification_deliveries/i }));

    expect(onSelectQueue).toHaveBeenCalledWith("notification_deliveries");
  });

  it("renders selected queue rows as operator-ready work items", () => {
    render(
      <OpsDiagnosticsPage
        diagnostics={fakeDiagnostics}
        loading={false}
        queue={fakeNotificationQueue}
        selectedQueueName="notification_deliveries"
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByText("delivery-1")).toBeInTheDocument();
    expect(screen.getByText("尝试 2/3")).toBeInTheDocument();
    expect(screen.getByText("notification_id: notification-1")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();
  });
});

const fakeDiagnostics: OpsDiagnostics = {
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
    gmgn_configured: true,
    okx_dex_configured: true,
    llm_configured: false,
  },
  database: { status: "ok", probe: "postgres_liveness" },
  collector: { status: "ok", details: { frames_received: 12 } },
  providers: [
    {
      provider: "gmgn",
      domain: "asset_market",
      configured: true,
      capabilities: ["quote_dex_exact"],
      state: "configured",
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
      queue_depth: 0,
      status: "ok",
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
      status: "blocked",
      reason: "dead_jobs_present",
    },
  ],
  domains: {
    news: { status: "ok", source_count: 3 },
    notifications: { status: "blocked", dead_jobs: 1 },
  },
  suggested_checks: [
    { id: "inspect_worker_status", label: "inspect worker queues" },
    { id: "inspect_news_sources", label: "inspect news sources" },
  ],
};

const fakeNotificationQueue = {
  schema_version: "ops.queue.v1",
  queue_name: "notification_deliveries",
  counts_by_status: { dead: 1, pending: 2, running: 1 },
  summary: fakeDiagnostics.queues[0],
  items: [
    {
      id: "delivery-1",
      status: "dead",
      attempt_count: 2,
      max_attempts: 3,
      updated_at_ms: 1_700_000_000_000,
      next_run_at_ms: 1_700_000_030_000,
      last_error_type: "RuntimeError",
      source: {
        notification_id: "notification-1",
        channel: "in_app",
      },
    },
  ],
};
