import { SignalLabPulse } from "@features/signal-lab";
import { tittyPulseFixture } from "@features/signal-lab/test/fixtures";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("keeps the bottom panel while removing the queue opener", () => {
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
              blocked_low_information_count: 0,
              dead_job_count: 0,
              market_ready_rate: 1,
            },
            summary: {
              trade_candidate: 1,
              token_watch: 0,
              risk_rejected_high_info: 0,
              blocked_low_information: 0,
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
    expect(screen.queryByText("打开队列")).not.toBeInTheDocument();
    const header = screen.getByRole("heading", { name: "Signal Pulse" }).closest("header");
    expect(header).not.toBeNull();
    expect(
      within(header!).getByText((_, node) => node?.textContent === "候选 1"),
    ).toBeInTheDocument();
    expect(
      within(header!).getByText((_, node) => node?.textContent === "代币 0"),
    ).toBeInTheDocument();
    expect(
      within(header!).getByText((_, node) => node?.textContent === "拒绝 0"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /TITTY/ }));

    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: tittyPulseFixture.candidate_id }),
    );
  });
});
