import { CockpitTopbar } from "@features/cockpit";
import { cleanup, render, screen } from "@testing-library/react";
import { appStatusFixture } from "@tests/fixtures/appRouteFixtures";
import { axe } from "jest-axe";
import { createRef } from "react";
import { MemoryRouter } from "react-router-dom";
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

  it("shows required status reasons when the runtime is not ready", () => {
    render(
      <MemoryRouter>
        <CockpitTopbar
          search={{ inputRef: createRef<HTMLInputElement>(), onSubmitQuery: vi.fn() }}
          status={{
            socketStatus: "connected",
            lastSocketMessageAt: 1_700_000_000_000,
            status: appStatusFixture({
              ok: false,
              reasons: ["news_provider_contract_error"],
            }),
            statusLoading: false,
            statusError: false,
            configReady: true,
          }}
          notifications={{ summary: null, drawerOpen: false, onToggleDrawer: vi.fn() }}
          onRefresh={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("not ready")).toHaveAttribute("title", "news_provider_contract_error");
  });
});
