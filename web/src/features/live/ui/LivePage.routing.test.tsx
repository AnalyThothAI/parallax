import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect } from "vitest";

import { LivePage } from "./LivePage";

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
                signalLabPulseData={null}
                selectedPulseItemId={null}
                signalPulseLoading={false}
                onOpenLab={() => {}}
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
  });
});
