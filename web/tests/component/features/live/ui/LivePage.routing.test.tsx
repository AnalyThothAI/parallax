import { LivePage } from "@features/live";
import { tittyPulseFixture } from "@features/signal-lab/test/fixtures";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect } from "vitest";

describe("LivePage", () => {
  it("renders within a route and exposes the live-page testid", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            element={
              <LivePage
                liveSignalTapeItems={[]}
                isRecentLoading={false}
                socketStatus="connected"
                selectedTapeEventId={null}
                onTapeSelect={() => {}}
                signalLabPulseData={{
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
                  },
                  items: [tittyPulseFixture],
                  returned_count: 1,
                  has_more: false,
                  next_cursor: null,
                }}
                hiddenSignalLabPulseData={null}
                signalPulseLoading={false}
                hiddenSignalPulseLoading={false}
                selectedPulseItemId={null}
                onSelectPulse={() => {}}
              />
            }
          >
            <Route index element={<div data-testid="child-content" />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("live-page")).toBeInTheDocument();
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Signal Pulse" })).toBeInTheDocument();
    expect(screen.queryByText("打开队列")).not.toBeInTheDocument();
  });
});
