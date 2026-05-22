import { SignalLabPulse } from "@features/signal-lab";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { tittyPulseFixture } from "@tests/fixtures/signal-lab";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => cleanup());

describe("SignalLabPulse", () => {
  it("renders compact loading rows", () => {
    render(
      <MemoryRouter>
        <SignalLabPulse isLoading data={undefined} onSelect={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("loading signal pulse")).toBeInTheDocument();
  });

  it("keeps compact visibility tabs while removing summary chrome", () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <SignalLabPulse
          data={{
            query: { window: "1h", scope: "all" },
            health: {
              pulse_ready: true,
              agent_worker_running: true,
              candidate_count: 1,
              public_candidate_count: 1,
              hidden_candidate_count: 2,
              blocked_low_information_count: 0,
              dead_job_count: 0,
              market_ready_rate: 1,
            },
            summary: {
              trade_candidate: 1,
              token_watch: 0,
              risk_rejected_high_info: 0,
            },
            items: [tittyPulseFixture],
            returned_count: 1,
            has_more: false,
            next_cursor: null,
          }}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Signal Pulse" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "公开 1" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("tab", { name: "隐藏 2" })).toHaveAttribute("data-state", "inactive");
    expect(screen.queryByLabelText("signal pulse summary")).not.toBeInTheDocument();
    expect(screen.queryByText("打开队列")).not.toBeInTheDocument();
    const header = screen.getByRole("heading", { name: "Signal Pulse" }).closest("header");
    expect(header).not.toBeNull();
    expect(screen.queryByText((_, node) => node?.textContent === "候选 1")).not.toBeInTheDocument();
    expect(screen.queryByText((_, node) => node?.textContent === "代币 0")).not.toBeInTheDocument();
    expect(screen.queryByText((_, node) => node?.textContent === "拒绝 0")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /TITTY/ }));

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: tittyPulseFixture.candidate_id }),
    );
  });

  it("switches the compact panel to hidden Signal Pulse rows without summary chrome", () => {
    const onSelect = vi.fn();
    const hiddenFixture = {
      ...tittyPulseFixture,
      candidate_id: "pulse-hidden-titty",
      display_status: "hidden_invalid_output",
      symbol: "HIDT",
    };
    render(
      <MemoryRouter>
        <SignalLabPulse
          data={{
            query: { window: "4h", scope: "all", visibility: "public" },
            health: {
              pulse_ready: true,
              agent_worker_running: true,
              candidate_count: 4,
              public_candidate_count: 1,
              hidden_candidate_count: 3,
              blocked_low_information_count: 0,
              dead_job_count: 0,
              market_ready_rate: 1,
            },
            summary: {
              trade_candidate: 1,
              token_watch: 0,
              risk_rejected_high_info: 0,
            },
            items: [tittyPulseFixture],
            returned_count: 1,
            has_more: false,
            next_cursor: null,
          }}
          hiddenData={{
            query: { window: "4h", scope: "all", visibility: "hidden" },
            health: {
              pulse_ready: true,
              agent_worker_running: true,
              candidate_count: 4,
              public_candidate_count: 1,
              hidden_candidate_count: 3,
              blocked_low_information_count: 0,
              dead_job_count: 0,
              market_ready_rate: 1,
            },
            summary: {
              trade_candidate: 1,
              token_watch: 0,
              risk_rejected_high_info: 0,
            },
            items: [hiddenFixture],
            returned_count: 1,
            has_more: false,
            next_cursor: null,
          }}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "隐藏 3" }));

    expect(screen.getByRole("button", { name: /TITTY/ })).toBeInTheDocument();
    expect(screen.getByText("隐藏 invalid output")).toBeInTheDocument();
    expect(screen.getAllByText((_, node) => node?.textContent === "隐藏 3")).toHaveLength(1);
    expect(screen.queryByLabelText("signal pulse summary")).not.toBeInTheDocument();
    expect(screen.queryByText((_, node) => node?.textContent === "总计 4")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /TITTY/ }));

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: "pulse-hidden-titty" }),
    );
  });
});
