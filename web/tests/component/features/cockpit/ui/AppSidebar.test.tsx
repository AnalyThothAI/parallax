import { AppSidebar } from "@features/cockpit/ui/AppSidebar";
import { SidebarProvider } from "@shared/ui/sidebar";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("renders exactly six flat Macro destinations when the branch is opened", () => {
    renderSidebar({ route: "/" });

    expect(screen.getByRole("button", { name: "展开宏观" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("link", { name: "总览" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开宏观" }));

    const expectedLinks = [
      ["总览", "/macro"],
      ["跨资产", "/macro/cross-asset"],
      ["利率与通胀", "/macro/rates-inflation"],
      ["增长与就业", "/macro/growth-labor"],
      ["流动性与资金", "/macro/liquidity-funding"],
      ["信用", "/macro/credit"],
    ] as const;
    for (const [label, href] of expectedLinks) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", href);
    }
    expect(
      screen
        .getAllByRole("link")
        .filter((link) => expectedLinks.some(([, href]) => link.getAttribute("href") === href)),
    ).toHaveLength(7);
  });

  it("marks only the active flat Macro child as current", () => {
    renderSidebar({ route: "/macro/credit" });

    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");
    expect(screen.getByRole("button", { name: "收起宏观" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("link", { name: "信用" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("does not expose any retired nested Macro categories or leaves", () => {
    renderSidebar({ route: "/macro" });

    for (const label of [
      "大类资产",
      "利率",
      "流动性",
      "经济数据",
      "波动率",
      "美股",
      "收益率曲线",
      "相关性",
      "美联储",
      "Dashboard",
      "CDS 代理",
    ]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
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
