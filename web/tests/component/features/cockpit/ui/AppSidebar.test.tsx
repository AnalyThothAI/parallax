import { AppSidebar, type AppSidebarBadges } from "@features/cockpit/ui/AppSidebar";
import { SidebarProvider } from "@shared/ui/sidebar";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("AppSidebar", () => {
  it("renders the product navigation groups in order", () => {
    renderSidebar();

    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    const headings = within(navigation).getAllByRole("heading", { level: 2 });
    expect(headings.map((heading) => heading.textContent?.trim())).toEqual([
      "Radar",
      "Intel",
      "System",
    ]);
  });

  it("renders a semantic footer status surface without shortcut instructions", () => {
    renderSidebar();

    expect(screen.queryByText(/cmd\+b sidebar \/ search/i)).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Desk status" })).toBeInTheDocument();
  });

  it("keeps nested Macro active while only marking the Correlation leaf as current", () => {
    renderSidebar({ route: "/macro/assets/correlation" });

    const macroLink = screen.getByRole("link", { name: /Macro/i });
    expect(macroLink).toHaveAttribute("href", "/macro");
    expect(macroLink).toHaveAttribute("data-active", "true");
    expect(macroLink).not.toHaveAttribute("aria-current");

    const correlationLink = screen.getByRole("link", { name: /Correlation/i });
    expect(correlationLink).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("renders numeric and string badges without empty chips for missing badge keys", () => {
    renderSidebar({ badges: { news: "8+", token: 0 } });

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("8+")).toBeInTheDocument();
    expect(document.querySelectorAll('[data-sidebar="menu-badge"]')).toHaveLength(2);
  });
});

function renderSidebar({
  badges = { news: "8+", stocks: 2, token: 4 },
  route = "/",
}: {
  badges?: AppSidebarBadges;
  route?: string;
} = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <SidebarProvider>
        <AppSidebar badges={badges} />
      </SidebarProvider>
    </MemoryRouter>,
  );
}
