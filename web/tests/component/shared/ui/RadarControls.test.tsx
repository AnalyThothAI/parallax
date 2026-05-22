import { RadarControls } from "@shared/ui/RadarControls";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("RadarControls", () => {
  it("uses shared toggle primitives for radar window and scope changes", () => {
    const onWindowChange = vi.fn();
    const onScopeChange = vi.fn();

    render(
      <RadarControls
        windowKey="1h"
        scope="matched"
        handles="@alpha"
        onWindowChange={onWindowChange}
        onScopeChange={onScopeChange}
        onHandlesChange={() => undefined}
      />,
    );

    const windowGroup = screen.getByLabelText("radar window");
    expect(windowGroup).toHaveAttribute("data-slot", "toggle-group");
    expect(within(windowGroup).getByRole("radio", { name: "1h" })).toHaveAttribute(
      "data-state",
      "on",
    );

    fireEvent.click(within(windowGroup).getByRole("radio", { name: "4h" }));
    expect(onWindowChange).toHaveBeenCalledWith("4h");
    onWindowChange.mockClear();
    fireEvent.click(within(windowGroup).getByRole("radio", { name: "1h" }));
    expect(onWindowChange).not.toHaveBeenCalled();

    const scopeGroup = screen.getByLabelText("token flow scope");
    expect(scopeGroup).toHaveAttribute("data-slot", "toggle-group");
    expect(within(scopeGroup).getByRole("radio", { name: "watched" })).toHaveAttribute(
      "data-state",
      "on",
    );

    fireEvent.click(within(scopeGroup).getByRole("radio", { name: "all" }));
    expect(onScopeChange).toHaveBeenCalledWith("all");
    onScopeChange.mockClear();
    fireEvent.click(within(scopeGroup).getByRole("radio", { name: "watched" }));
    expect(onScopeChange).not.toHaveBeenCalled();
  });
});
