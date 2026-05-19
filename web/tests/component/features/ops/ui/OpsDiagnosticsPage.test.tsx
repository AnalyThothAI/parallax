import { OpsDiagnosticsPage } from "@features/ops";
import type { OpsDiagnostics } from "@features/ops";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("OpsDiagnosticsPage", () => {
  it("renders the main diagnostic regions and queue selection", () => {
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

    expect(screen.getByText("Ops Diagnostics")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Providers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Workers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Queues" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Config Source" })).toBeInTheDocument();
    expect(screen.getByText("pulse_agent_jobs")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /open queue pulse_agent_jobs/i }));

    expect(onSelectQueue).toHaveBeenCalledWith("pulse_agent_jobs");
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
    app_home: "/Users/qinghuan/.gmgn-twitter-intel",
    config_path: "/Users/qinghuan/.gmgn-twitter-intel/config.yaml",
    workers_config_path: "/Users/qinghuan/.gmgn-twitter-intel/workers.yaml",
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
      queue_name: "pulse_agent_jobs",
      table: "pulse_agent_jobs",
      worker_name: "pulse_candidate",
      counts_by_status: { failed: 1 },
      due_count: 0,
      running_count: 0,
      dead_count: 0,
      failed_count: 1,
      status: "degraded",
      reason: "retryable_failures_present",
    },
  ],
  domains: {
    pulse: { status: "degraded", failed_jobs_4h: 1 },
    news: { status: "ok", source_count: 3 },
  },
  suggested_checks: [],
};
