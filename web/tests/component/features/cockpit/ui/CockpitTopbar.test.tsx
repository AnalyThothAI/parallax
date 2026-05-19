import { CockpitTopbar } from "@features/cockpit";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { createRef } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

describe("CockpitTopbar", () => {
  it("renders accessible search, status, and notification controls", async () => {
    const { container } = render(
      <MemoryRouter>
        <CockpitTopbar
          search={{ inputRef: createRef<HTMLInputElement>(), onSubmitQuery: vi.fn() }}
          status={{
            socketStatus: "connected",
            lastSocketMessageAt: 1_700_000_000_000,
            status: null,
            statusLoading: false,
            statusError: false,
            configReady: true,
          }}
          stats={{
            tokenItemsCount: 3,
            windowKey: "1h",
            signalLabSummaryTrade: 1,
            signalLabSummaryToken: 2,
            signalLabSummaryRisk: 0,
          }}
          notifications={{ summary: null, drawerOpen: false, onToggleDrawer: vi.fn() }}
          onRefresh={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("textbox", { name: "global search" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: /WebSocket connected/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open ops diagnostics" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "notifications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("routes to ops diagnostics from the banner entry", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <CockpitTopbar
          search={{ inputRef: createRef<HTMLInputElement>(), onSubmitQuery: vi.fn() }}
          status={{
            socketStatus: "connected",
            lastSocketMessageAt: 1_700_000_000_000,
            status: null,
            statusLoading: false,
            statusError: false,
            configReady: true,
          }}
          stats={{
            tokenItemsCount: 3,
            windowKey: "1h",
            signalLabSummaryTrade: 1,
            signalLabSummaryToken: 2,
            signalLabSummaryRisk: 0,
          }}
          notifications={{ summary: null, drawerOpen: false, onToggleDrawer: vi.fn() }}
          onRefresh={vi.fn()}
        />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open ops diagnostics" }));

    expect(screen.getByTestId("location-pathname")).toHaveTextContent("/ops");
  });
});

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location-pathname">{location.pathname}</span>;
}
