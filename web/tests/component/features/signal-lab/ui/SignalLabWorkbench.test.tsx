import { SignalLabWorkbench } from "@features/signal-lab/ui/SignalLabWorkbench";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("SignalLabWorkbench", () => {
  it("shows hold-publish health instead of a plain empty queue", () => {
    render(
      <SignalLabWorkbench
        data={{
          query: { window: "1h", scope: "all" },
          health: {
            pulse_ready: false,
            public_ready: false,
            agent_worker_running: true,
            candidate_count: 5,
            public_candidate_count: 0,
            blocked_low_information_count: 0,
            dead_job_count: 0,
            market_ready_rate: 0,
            publish_status: "hold_publish",
            reasons: ["agent_failure_rate_hold"],
            hidden_hold_publish_4h: 5,
            public_candidates_4h: 0,
          },
          summary: {
            trade_candidate: 0,
            token_watch: 0,
            risk_rejected_high_info: 0,
          },
          items: [],
          returned_count: 0,
          has_more: false,
          next_cursor: null,
        }}
        handleFilter=""
        searchFilter=""
        statusFilter="all"
        visibilityFilter="public"
        windowLabel="1h"
        onClearFilters={vi.fn()}
        onHandleChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSearchChange={vi.fn()}
        onSelectAccountEvent={vi.fn()}
        onSelect={vi.fn()}
        onStatusChange={vi.fn()}
        onVisibilityChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("status", { name: "Signal Pulse health" })).toHaveTextContent(
      "发布暂停",
    );
    expect(screen.getByRole("status", { name: "Signal Pulse health" })).toHaveTextContent(
      "agent failure rate hold",
    );
    expect(screen.getByRole("status", { name: "Signal Pulse health" })).toHaveTextContent(
      "public 0",
    );
    expect(screen.getByRole("status", { name: "Signal Pulse health" })).toHaveTextContent(
      "hidden 5",
    );
  });

  it("lets operators switch to the hidden Signal Pulse lane from tabs", () => {
    const onVisibilityChange = vi.fn();
    render(
      <SignalLabWorkbench
        data={{
          query: { window: "1h", scope: "all", visibility: "public" },
          health: {
            pulse_ready: true,
            public_ready: true,
            agent_worker_running: true,
            candidate_count: 8,
            public_candidate_count: 3,
            hidden_candidate_count: 5,
            blocked_low_information_count: 0,
            dead_job_count: 0,
            market_ready_rate: 1,
          },
          summary: {
            trade_candidate: 1,
            token_watch: 2,
            risk_rejected_high_info: 0,
          },
          items: [],
          returned_count: 0,
          has_more: false,
          next_cursor: null,
        }}
        handleFilter=""
        searchFilter=""
        statusFilter="all"
        visibilityFilter="public"
        windowLabel="1h"
        onClearFilters={vi.fn()}
        onHandleChange={vi.fn()}
        onLoadMore={vi.fn()}
        onSearchChange={vi.fn()}
        onSelectAccountEvent={vi.fn()}
        onSelect={vi.fn()}
        onStatusChange={vi.fn()}
        onVisibilityChange={onVisibilityChange}
      />,
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: /隐藏/ }), {
      button: 0,
      ctrlKey: false,
    });

    expect(onVisibilityChange).toHaveBeenCalledWith("hidden");
  });
});
