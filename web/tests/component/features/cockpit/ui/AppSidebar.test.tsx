import { AppSidebar } from "@features/cockpit/ui/AppSidebar";
import { SidebarProvider } from "@shared/ui/sidebar";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

describe("AppSidebar", () => {
  it("renders grouped navigation with badges and nested active routes", () => {
    render(
      <MemoryRouter initialEntries={["/macro/assets/correlation"]}>
        <SidebarProvider>
          <AppSidebar badges={{ news: "8+", stocks: 2, token: 4 }} />
        </SidebarProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Token Radar/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /Stocks/i })).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /News/i })).toBeInTheDocument();
    expect(screen.getByText("8+")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Macro/i })).toHaveAttribute("href", "/macro");
    expect(screen.getByRole("link", { name: /Correlation/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
