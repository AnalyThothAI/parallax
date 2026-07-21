import { LivePage } from "@features/live";
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
                mobileTask="radar"
                onMobileTaskChange={() => {}}
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
    expect(screen.getByRole("heading", { name: "实时信号 Tape" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Radar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tape" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lab" })).not.toBeInTheDocument();
  });
});
