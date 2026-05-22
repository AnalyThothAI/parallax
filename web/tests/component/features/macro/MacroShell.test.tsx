import { MacroShell } from "@features/macro/ui/shell/MacroShell";
import { screen } from "@testing-library/react";
import { macroModuleFixture } from "@tests/fixtures/macroFixture";
import { renderWithProviders } from "@tests/render/renderWithProviders";
import { describe, expect, it } from "vitest";

describe("MacroShell", () => {
  it("renders the module header, gaps, and caller content without page-local navigation", () => {
    renderWithProviders(
      <MacroShell moduleId="assets/equities" module={macroModuleFixture()}>
        <section aria-label="module content">Backend content slot</section>
      </MacroShell>,
      { route: "/macro/assets/equities" },
    );

    expect(screen.getByRole("heading", { name: "美股" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("href", "/macro");
    expect(screen.getByRole("link", { name: "大类资产" })).toHaveAttribute("href", "/macro/assets");
    expect(screen.queryByRole("navigation", { name: "Macro modules" })).not.toBeInTheDocument();
    expect(screen.getByText("截至 2026-05-20")).toBeInTheDocument();
    expect(screen.getByText("部分可用")).toBeInTheDocument();
    expect(screen.getByText("equity_breadth_missing")).toBeInTheDocument();
    expect(screen.getByText("Backend content slot")).toBeInTheDocument();
    expect(screen.queryByText(/frontend score/i)).not.toBeInTheDocument();
  });
});
