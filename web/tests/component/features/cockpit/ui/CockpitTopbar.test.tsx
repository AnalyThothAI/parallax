import { CockpitTopbar } from "@features/cockpit";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { createRef } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

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
    expect(screen.getByRole("button", { name: "notifications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
