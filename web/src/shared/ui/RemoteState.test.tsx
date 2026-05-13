import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { IconButton } from "./IconButton";
import { PanelSkeleton, RouteStatePanel, SkeletonRows } from "./RemoteState";

describe("RemoteState shared UI", () => {
  it("renders accessible loading and empty/error panels", async () => {
    const { container } = render(
      <main>
        <SkeletonRows label="loading remote rows" />
        <PanelSkeleton label="loading panel rows" />
        <RouteStatePanel title="No rows">Try a wider window.</RouteStatePanel>
      </main>,
    );

    expect(screen.getByLabelText("loading remote rows")).toBeInTheDocument();
    expect(screen.getByText("No rows")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders an aria-labelled icon button", async () => {
    const { container } = render(
      <IconButton aria-label="refresh data">
        <span aria-hidden>R</span>
      </IconButton>,
    );

    expect(screen.getByRole("button", { name: "refresh data" })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
