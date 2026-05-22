import * as PageState from "@shared/ui/PageState";
import { Button } from "@shared/ui/button";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

describe("PageState shared UI", () => {
  it("renders accessible loading and table skeleton states", async () => {
    const { container } = render(
      <section>
        <PageState.Loading layout="route" rows={2} label="loading route data" />
        <PageState.TableSkeleton rows={3} compact label="loading compact table" />
      </section>,
    );

    expect(screen.getByRole("status", { name: "loading route data" })).toHaveClass(
      "page-state-loading",
      "page-state-layout-route",
    );
    expect(screen.getByRole("status", { name: "loading compact table" })).toHaveClass(
      "page-state-table-skeleton",
      "page-state-table-skeleton-compact",
    );
    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(15);
    expect(container.querySelector(".remote-state-loading")).not.toBeInTheDocument();
    expect(container.querySelector(".skeleton-rows")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders empty state hints and caller-provided actions", async () => {
    const { container } = render(
      <PageState.Empty
        title="No rows"
        hint="Try a wider window."
        action={<Button type="button">Reset filters</Button>}
      />,
    );

    expect(screen.getByText("No rows")).toBeInTheDocument();
    expect(screen.getByText("Try a wider window.")).toBeInTheDocument();
    expect(screen.getByText("No rows").closest(".page-state-empty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset filters" })).toHaveAttribute(
      "data-slot",
      "button",
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders error alerts with canonical retry buttons", async () => {
    const onRetry = vi.fn();
    const { container } = render(
      <PageState.Error error={new Error("backend unavailable")} onRetry={onRetry} />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("page-state-error");
    expect(alert).toHaveTextContent("backend unavailable");
    const retry = within(alert).getByRole("button", { name: "Retry" });
    expect(retry).toHaveAttribute("data-slot", "button");

    fireEvent.click(retry);

    expect(onRetry).toHaveBeenCalledOnce();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks stale content busy while retaining settled children", () => {
    render(
      <PageState.Stale updating>
        <span>cached rows</span>
      </PageState.Stale>,
    );

    expect(screen.getByText("cached rows").parentElement).toHaveClass("page-state-stale");
    expect(screen.getByText("cached rows").parentElement).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Updating")).toHaveClass("sr-only");
  });
});
