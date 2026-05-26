import { AppSidebar } from "@features/cockpit/ui/AppSidebar";
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

    const macroLink = screen.getByRole("link", { name: "宏观" });
    expect(macroLink).toHaveAttribute("href", "/macro");
    expect(macroLink).toHaveAttribute("data-active", "true");
    expect(macroLink).not.toHaveAttribute("aria-current");

    const correlationLink = screen.getByRole("link", { name: "相关性" });
    expect(correlationLink).toHaveAttribute("href", "/macro/assets/correlation");
    expect(correlationLink).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("keeps the Macro app parent branch-active while only the overview child is current", () => {
    renderSidebar({ route: "/macro" });

    const macroLink = screen.getByRole("link", { name: "宏观" });
    expect(macroLink).toHaveAttribute("href", "/macro");
    expect(macroLink).toHaveAttribute("data-active", "true");
    expect(macroLink).not.toHaveAttribute("aria-current");

    const overviewLink = screen.getByRole("link", { name: "总览" });
    expect(overviewLink).toHaveAttribute("href", "/macro");
    expect(overviewLink).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("renders the full nested Macro tree and marks only the active leaf current", () => {
    renderSidebar({ route: "/macro/assets/equities" });

    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");
    const assetLink = screen.getByRole("link", { name: "大类资产" });
    expect(assetLink).toHaveAttribute("data-active", "true");
    expect(assetLink).toHaveAttribute("href", "/macro/assets");
    expect(assetLink).not.toHaveAttribute("aria-current");

    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute(
      "href",
      "/macro/assets/equities",
    );
    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("marks an exact nested Macro section route current without marking child leaves current", () => {
    renderSidebar({ route: "/macro/assets" });

    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");

    const assetLink = screen.getByRole("link", { name: "大类资产" });
    expect(assetLink).toHaveAttribute("data-active", "true");
    expect(assetLink).toHaveAttribute("href", "/macro/assets");
    expect(assetLink).toHaveAttribute("aria-current", "page");

    expect(screen.getByRole("link", { name: "美股" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "相关性" })).not.toHaveAttribute("aria-current");
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("keeps navigation free of server-backed badges", () => {
    renderSidebar();

    expect(screen.getByRole("link", { name: "Token Radar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Stocks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "News" })).toBeInTheDocument();
    expect(document.querySelectorAll('[data-sidebar="menu-badge"]')).toHaveLength(0);
  });
});

function renderSidebar({
  route = "/",
}: {
  route?: string;
} = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <SidebarProvider>
        <AppSidebar />
      </SidebarProvider>
    </MemoryRouter>,
  );
}
