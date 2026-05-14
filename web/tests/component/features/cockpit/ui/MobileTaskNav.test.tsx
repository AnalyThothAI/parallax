import { MobileTaskNav } from "@features/cockpit";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("MobileTaskNav", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders only the primary cockpit tasks", () => {
    const onChange = vi.fn();

    render(<MobileTaskNav activeTask="radar" onTaskChange={onChange} />);

    expect(screen.getByRole("navigation", { name: "mobile cockpit tasks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Lab" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tape" }));

    expect(onChange).toHaveBeenCalledWith("tape");
  });

  it("switches into the lab task without a selected sidecar state", () => {
    const onChange = vi.fn();

    render(<MobileTaskNav activeTask="lab" onTaskChange={onChange} />);

    expect(screen.getByRole("button", { name: "Lab" })).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByRole("button", { name: "Radar" }));

    expect(onChange).toHaveBeenCalledWith("radar");
  });
});
