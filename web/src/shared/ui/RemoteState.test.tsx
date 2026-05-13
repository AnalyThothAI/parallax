import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { IconButton } from "./IconButton";
import { PanelSkeleton, RemoteState, RouteStatePanel, SkeletonRows } from "./RemoteState";

describe("RemoteState shared UI", () => {
  it("renders accessible loading and empty/error panels", async () => {
    const { container } = render(
      <section>
        <SkeletonRows label="loading remote rows" />
        <PanelSkeleton label="loading panel rows" />
        <RouteStatePanel title="No rows">Try a wider window.</RouteStatePanel>
      </section>,
    );

    expect(screen.getByLabelText("loading remote rows")).toBeInTheDocument();
    expect(screen.getByText("No rows")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders an aria-labelled icon button", async () => {
    const { container } = render(
      <IconButton aria-label="refresh data" className="extra-action">
        <span aria-hidden>R</span>
      </IconButton>,
    );

    expect(screen.getByRole("button", { name: "refresh data" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "refresh data" })).toHaveClass(
      "icon-button",
      "extra-action",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("exposes named remote state primitives for loading, empty, error, and stale content", async () => {
    const { container } = render(
      <section>
        <RemoteState.Loading layout="route" rows={2} label="loading route data" />
        <RemoteState.Empty title="No rows" hint="Try a wider window." />
        <RemoteState.Error error={new Error("backend unavailable")} onRetry={() => undefined} />
        <RemoteState.Stale updating>
          <span>cached rows</span>
        </RemoteState.Stale>
      </section>,
    );

    const canvas = within(container);
    expect(canvas.getByRole("status", { name: "loading route data" })).toHaveClass(
      "remote-state-loading",
      "route",
    );
    expect(canvas.getByText("No rows")).toBeInTheDocument();
    expect(canvas.getByRole("alert")).toHaveTextContent("backend unavailable");
    expect(canvas.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(canvas.getByText("cached rows").parentElement).toHaveAttribute("aria-busy", "true");
    expect(await axe(container)).toHaveNoViolations();
  });
});
