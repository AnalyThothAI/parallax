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

  it("does not expose the hard-deleted Correlation leaf under Macro assets", () => {
    renderSidebar({ route: "/macro/assets" });

    const macroLink = screen.getByRole("link", { name: "宏观" });
    expect(macroLink).toHaveAttribute("href", "/macro");
    expect(macroLink).toHaveAttribute("data-active", "true");
    expect(macroLink).not.toHaveAttribute("aria-current");

    const assetLink = screen.getByRole("link", { name: "大类资产" });
    expect(assetLink).toHaveAttribute("href", "/macro/assets");
    expect(assetLink).toHaveAttribute("data-active", "true");
    expect(assetLink).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "展开大类资产" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    fireEvent.click(screen.getByRole("button", { name: "展开大类资产" }));
    expect(screen.queryByRole("link", { name: "相关性" })).not.toBeInTheDocument();
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

  it("keeps active nested Macro category collapsed until opened", () => {
    renderSidebar({ route: "/macro/assets/equities" });

    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");
    expect(screen.getByRole("button", { name: "收起宏观" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    const assetLink = screen.getByRole("link", { name: "大类资产" });
    expect(assetLink).toHaveAttribute("data-active", "true");
    expect(assetLink).toHaveAttribute("href", "/macro/assets");
    expect(assetLink).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "展开大类资产" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("link", { name: "美股" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开大类资产" }));
    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute(
      "href",
      "/macro/assets/equities",
    );
    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "收益率曲线" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { current: "page" })).toHaveLength(1);
  });

  it("keeps nested macro branches collapsed until opened", () => {
    renderSidebar({ route: "/" });

    expect(screen.getByRole("button", { name: "展开宏观" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("link", { name: "美股" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "展开宏观" }));

    expect(screen.getByRole("link", { name: "大类资产" })).toHaveAttribute("href", "/macro/assets");
    expect(screen.getByRole("button", { name: "展开大类资产" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: "展开大类资产" }));

    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute(
      "href",
      "/macro/assets/equities",
    );
  });

  it("does not expose hard-deleted macro leaves in the primary sidebar", () => {
    renderSidebar({ route: "/macro" });

    fireEvent.click(screen.getByRole("button", { name: "收起宏观" }));
    fireEvent.click(screen.getByRole("button", { name: "展开宏观" }));
    fireEvent.click(screen.getByRole("button", { name: "展开利率" }));
    fireEvent.click(screen.getByRole("button", { name: "展开信用" }));

    expect(screen.queryByRole("link", { name: "美联储" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "拍卖" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "FOMC 声明" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "美联储讲话" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "加密衍生品" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "全球美元" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "资金面暗流" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "消费" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "CDS 代理" })).not.toBeInTheDocument();
  });

  it("links macro category parents to default children without creating current index links", () => {
    renderSidebar({ route: "/macro/assets/equities" });

    expect(screen.getByRole("link", { name: "宏观" })).toHaveAttribute("data-active", "true");

    const assetLink = screen.getByRole("link", { name: "大类资产" });
    expect(assetLink).toHaveAttribute("data-active", "true");
    expect(assetLink).toHaveAttribute("href", "/macro/assets");
    expect(assetLink).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "利率" })).toHaveAttribute(
      "href",
      "/macro/rates/fed-funds",
    );
    expect(screen.queryByRole("link", { name: "美联储" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "流动性" })).toHaveAttribute(
      "href",
      "/macro/liquidity/rrp-tga",
    );
    expect(screen.getByRole("link", { name: "经济数据" })).toHaveAttribute(
      "href",
      "/macro/economy/gdp",
    );
    expect(screen.getByRole("link", { name: "波动率" })).toHaveAttribute(
      "href",
      "/macro/volatility/vix",
    );
    expect(screen.getByRole("link", { name: "信用" })).toHaveAttribute(
      "href",
      "/macro/credit/stress",
    );

    expect(screen.queryByRole("link", { name: "美股" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开大类资产" }));
    expect(screen.getByRole("link", { name: "美股" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "相关性" })).not.toBeInTheDocument();
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
