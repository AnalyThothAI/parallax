import { SignalLabPulse } from "@features/signal-lab";
import { tittyPulseFixture } from "@features/signal-lab/test/fixtures";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  it("keeps the bottom panel without compact visibility or summary chrome", () => {
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
    expect(screen.queryByRole("tab", { name: /公开/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /隐藏/ })).not.toBeInTheDocument();
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

  it("keeps compact Signal Pulse focused on public rows when hidden data exists", () => {
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

    expect(screen.getByRole("button", { name: /TITTY/ })).toBeInTheDocument();
    expect(screen.queryByText("隐藏 invalid output")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /隐藏/ })).not.toBeInTheDocument();
    expect(screen.queryByText((_, node) => node?.textContent === "总计 4")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /TITTY/ }));

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: tittyPulseFixture.candidate_id }),
    );
  });
});
