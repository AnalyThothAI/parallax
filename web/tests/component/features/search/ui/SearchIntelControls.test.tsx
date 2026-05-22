import { SearchIntelControls } from "@features/search/ui/SearchIntelControls";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

describe("SearchIntelControls", () => {
  it("uses shared toggle primitives for search window and scope changes", () => {
    const onRouteChange = vi.fn();

    render(
      <SearchIntelControls
        routeState={{ q: "$RKC", window: "24h", scope: "all" }}
        onRouteChange={onRouteChange}
      />,
    );

    const windowGroup = screen.getByRole("group", { name: "search window" });
    expect(windowGroup).toHaveAttribute("data-slot", "toggle-group");
    expect(within(windowGroup).getByRole("radio", { name: "24h" })).toHaveAttribute(
      "data-state",
      "on",
    );

    fireEvent.click(within(windowGroup).getByRole("radio", { name: "1h" }));
    expect(onRouteChange).toHaveBeenCalledWith({ window: "1h" });
    onRouteChange.mockClear();
    fireEvent.click(within(windowGroup).getByRole("radio", { name: "24h" }));
    expect(onRouteChange).not.toHaveBeenCalled();

    const scopeGroup = screen.getByRole("group", { name: "search scope" });
    expect(scopeGroup).toHaveAttribute("data-slot", "toggle-group");
    expect(within(scopeGroup).getByRole("radio", { name: "all" })).toHaveAttribute(
      "data-state",
      "on",
    );

    fireEvent.click(within(scopeGroup).getByRole("radio", { name: "matched" }));
    expect(onRouteChange).toHaveBeenCalledWith({ scope: "matched" });
    onRouteChange.mockClear();
    fireEvent.click(within(scopeGroup).getByRole("radio", { name: "all" }));
    expect(onRouteChange).not.toHaveBeenCalled();
  });
});
