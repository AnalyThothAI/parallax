import { OpsDiagnosticsPage } from "@features/ops";
import type { OpsDiagnostics } from "@features/ops";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { notificationSummaryFixture } from "@tests/fixtures/appRouteFixtures";
import {
  activeOpsAgentExecutionFixture,
  opsDiagnosticsFixture,
  opsQueueFixture,
} from "@tests/fixtures/opsFixture";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("OpsDiagnosticsPage", () => {
  afterEach(cleanup);

  it("renders the command-center summary, chain lanes, and queue selection", () => {
    const onSelectQueue = vi.fn();
    const diagnostics = opsDiagnosticsFixture();

    render(
      <OpsDiagnosticsPage
        diagnostics={diagnostics}
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
    const diagnostics = opsDiagnosticsFixture();
    render(
      <OpsDiagnosticsPage
        diagnostics={diagnostics}
        loading={false}
        queue={opsQueueFixture()}
        selectedQueueName="notification_deliveries"
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByText("delivery-1")).toBeInTheDocument();
    expect(screen.getByText("尝试 2/3")).toBeInTheDocument();
    expect(screen.getByText("notification_id: notification-1")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();
  });

  it("fails closed when the diagnostics boundary is missing", () => {
    const malformed = { ...opsDiagnosticsFixture() } as Record<string, unknown>;
    delete malformed.overall;

    render(
      <OpsDiagnosticsPage
        diagnostics={malformed as unknown as OpsDiagnostics}
        loading={false}
        queue={null}
        selectedQueueName={null}
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("ops_current_contract:diagnostics");
    expect(screen.queryByText("没有阻塞项")).not.toBeInTheDocument();
  });

  it("does not call a degraded but unlocalized diagnostic healthy", () => {
    const diagnostics = opsDiagnosticsFixture();
    diagnostics.queues = [];
    diagnostics.domains.notifications = { status: "ok", summary: notificationSummaryFixture() };
    diagnostics.overall = {
      status: "degraded",
      severity: "warning",
      reasons: ["unlocalized_runtime_degradation"],
      section_status_counts: { degraded: 1 },
    };

    render(
      <OpsDiagnosticsPage
        diagnostics={diagnostics}
        loading={false}
        queue={null}
        selectedQueueName={null}
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByText("诊断未定位到具体阻塞项")).toBeInTheDocument();
    expect(screen.queryByText("没有阻塞项")).not.toBeInTheDocument();
  });

  it("describes an agent incident from the fixed lane policy", () => {
    const diagnostics = opsDiagnosticsFixture();
    diagnostics.agent_execution = {
      ...activeOpsAgentExecutionFixture(),
      status: "degraded",
      status_reason: "recent_timeout",
      error: "model timeout",
    };

    render(
      <OpsDiagnosticsPage
        diagnostics={diagnostics}
        loading={false}
        queue={null}
        selectedQueueName={null}
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByText("news.story_brief: model timeout")).toBeInTheDocument();
  });

  it("fails closed when selected queue data is malformed", () => {
    const malformedQueue = { ...opsQueueFixture() } as Record<string, unknown>;
    delete malformedQueue.status_filter;

    render(
      <OpsDiagnosticsPage
        diagnostics={opsDiagnosticsFixture()}
        loading={false}
        queue={malformedQueue as never}
        selectedQueueName="notification_deliveries"
        onSelectQueue={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("ops_current_contract:queue");
  });
});
