import { MacroShell } from "@features/macro/ui/shell/MacroShell";
import { screen } from "@testing-library/react";
import { macroModuleFixture } from "@tests/fixtures/macroFixture";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { describe, expect, it } from "vitest";

describe("MacroShell", () => {
  it("renders module navigation, provenance, gaps, and caller content without deriving analysis", () => {
    renderWithProviders(
      <MacroShell moduleId="assets/equities" module={macroModuleFixture()}>
        <section aria-label="module content">Backend content slot</section>
      </MacroShell>,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByRole("heading", { name: "Equities" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Macro" })).toHaveAttribute("href", "/macro");
    expect(screen.getByRole("link", { name: "Assets" })).toHaveAttribute(
      "href",
      "/macro/assets",
    );
    expect(screen.getByRole("navigation", { name: "Macro modules" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Equities" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("As of 2026-05-20")).toBeInTheDocument();
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.getByText("equity_breadth_missing")).toBeInTheDocument();
    expect(screen.getByText("Backend content slot")).toBeInTheDocument();
    expect(screen.queryByText(/frontend score/i)).not.toBeInTheDocument();
  });
});
