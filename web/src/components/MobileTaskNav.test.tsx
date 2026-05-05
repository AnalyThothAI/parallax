import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MobileTaskNav, type MobileTask } from "./MobileTaskNav";

describe("MobileTaskNav", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders task buttons with accessible active and disabled states", () => {
    const onChange = vi.fn();

    render(<MobileTaskNav activeTask="radar" detailAvailable={false} onTaskChange={onChange} />);

    expect(screen.getByRole("navigation", { name: "mobile cockpit tasks" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Radar" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Detail" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Tape" }));

    expect(onChange).toHaveBeenCalledWith("tape");
  });

  it("allows detail task when a selected object exists", () => {
    const onChange = vi.fn<(task: MobileTask) => void>();

    render(<MobileTaskNav activeTask="detail" detailAvailable onTaskChange={onChange} />);

    const detail = screen.getByRole("button", { name: "Detail" });
    expect(detail).toHaveAttribute("aria-current", "page");
    expect(detail).not.toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Lab" }));

    expect(onChange).toHaveBeenCalledWith("lab");
  });
});
